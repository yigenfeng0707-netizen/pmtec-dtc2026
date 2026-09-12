"""
Audit Logger - Hash-chained, tamper-evident operation logging.

Every gRPC call is logged with:
  - Timestamp, user_id, role, service, method, decision (ALLOWED/DENIED)
  - Source peer address
  - Hash chain: each entry's hash = SHA256(prev_hash + entry_data)

The audit trail is stored in SQLite for queryability and durability.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time


class AuditLogger:
    """Append-only, hash-chained audit logger backed by SQLite."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   REAL NOT NULL,
        user_id     TEXT NOT NULL,
        role        TEXT NOT NULL,
        service     TEXT NOT NULL,
        method      TEXT NOT NULL,
        decision    TEXT NOT NULL,
        peer        TEXT,
        detail      TEXT,
        entry_hash  TEXT NOT NULL,
        prev_hash   TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);
    CREATE INDEX IF NOT EXISTS idx_audit_service ON audit_log(service);
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "data", "persistence", "audit_log.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()
        self._last_hash = self._get_last_hash()

    def _get_last_hash(self) -> str:
        """Get the hash of the most recent entry, or genesis hash if empty."""
        cursor = self._conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row else "0" * 64

    def log(
        self,
        user_id: str,
        role: str,
        service: str,
        method: str,
        decision: str,
        peer: str = "",
        detail: str = "",
    ) -> str:
        """Log an audit entry and return its hash.

        Args:
            user_id: Authenticated user identifier
            role: User's role (commander/operator/observer)
            service: gRPC service name
            method: gRPC method name
            decision: ALLOWED or DENIED
            peer: Client peer address
            detail: Additional context (error message, etc.)
        """
        timestamp = time.time()
        prev_hash = self._last_hash

        entry_data = json.dumps(
            {
                "timestamp": timestamp,
                "user_id": user_id,
                "role": role,
                "service": service,
                "method": method,
                "decision": decision,
                "peer": peer,
                "detail": detail,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
        )
        entry_hash = hashlib.sha256(entry_data.encode("utf-8")).hexdigest()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_log
                    (timestamp, user_id, role, service, method, decision,
                     peer, detail, entry_hash, prev_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    user_id,
                    role,
                    service,
                    method,
                    decision,
                    peer,
                    detail,
                    entry_hash,
                    prev_hash,
                ),
            )
            self._conn.commit()
            self._last_hash = entry_hash

        return entry_hash

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire audit chain.

        Returns True if all entries' hash chains are valid, False if
        any entry has been tampered with.
        """
        cursor = self._conn.execute(
            "SELECT timestamp, user_id, role, service, method, decision, "
            "peer, detail, entry_hash, prev_hash FROM audit_log ORDER BY id ASC"
        )
        expected_prev = "0" * 64
        for row in cursor:
            entry_data = json.dumps(
                {
                    "timestamp": row[0],
                    "user_id": row[1],
                    "role": row[2],
                    "service": row[3],
                    "method": row[4],
                    "decision": row[5],
                    "peer": row[6],
                    "detail": row[7],
                    "prev_hash": row[9],
                },
                sort_keys=True,
            )
            computed_hash = hashlib.sha256(entry_data.encode("utf-8")).hexdigest()
            if computed_hash != row[8]:
                return False
            if row[9] != expected_prev:
                return False
            expected_prev = row[8]
        return True

    def query(
        self,
        user_id: str | None = None,
        service: str | None = None,
        decision: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
    ) -> list:
        """Query audit log entries with filters."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if service:
            query += " AND service = ?"
            params.append(service)
        if decision:
            query += " AND decision = ?"
            params.append(decision)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        columns = [
            "id",
            "timestamp",
            "user_id",
            "role",
            "service",
            "method",
            "decision",
            "peer",
            "detail",
            "entry_hash",
            "prev_hash",
        ]
        return [dict(zip(columns, row)) for row in cursor]

    def close(self):
        self._conn.close()
