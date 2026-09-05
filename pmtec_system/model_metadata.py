#!/usr/bin/env python3
"""
Model Metadata Manager - P8-v2

Provides versioned metadata for all AI models in PMTEC.
Each model file (e.g. pmtec_dqn_p7_v2.zip) has a companion .metadata.json
containing: algorithm, hyperparameters, training steps, evaluation metrics,
observation dimension, action space, creation timestamp, and source code hash.

Usage:
    from model_metadata import ModelMetadataManager

    mgr = ModelMetadataManager()
    mgr.write("pmtec_dqn_p7_v2.zip", {
        "algorithm": "DQN",
        "timesteps": 200000,
        "obs_dim": 182,
        "n_actions": 6,
        "evaluation": {"stealth_intercept_rate": 0.791},
        ...
    })
    meta = mgr.load("pmtec_dqn_p7_v2.zip")
    if not mgr.validate("pmtec_dqn_p7_v2.zip"):
        print("Model metadata mismatch!")
"""

import os
import json
import time
import hashlib
from typing import Optional

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "models",
)


class ModelMetadataManager:
    """Manages versioned metadata for AI model files."""

    def __init__(self, model_dir: str = None):
        self._model_dir = model_dir or _MODEL_DIR
        os.makedirs(self._model_dir, exist_ok=True)

    def _meta_path(self, model_filename: str) -> str:
        """Return metadata file path for a model file."""
        if model_filename.endswith(".metadata.json"):
            return os.path.join(self._model_dir, model_filename)
        base = (
            model_filename.rsplit(".", 1)[0]
            if "." in model_filename
            else model_filename
        )
        return os.path.join(self._model_dir, f"{base}.metadata.json")

    def _model_path(self, model_filename: str) -> str:
        """Return model file path."""
        return os.path.join(self._model_dir, model_filename)

    def _compute_file_hash(self, filepath: str) -> str:
        """Compute SHA-256 hash of a file (first 64KB for speed)."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            chunk = f.read(65536)
            h.update(chunk)
        return h.hexdigest()[:16]

    def write(self, model_filename: str, metadata: dict) -> str:
        """Write metadata for a model file.

        Args:
            model_filename: e.g. "pmtec_dqn_p7_v2.zip"
            metadata: dict with algorithm, timesteps, obs_dim, etc.

        Returns path to the metadata file.
        """
        meta_path = self._meta_path(model_filename)
        model_path = self._model_path(model_filename)

        # Enrich with standard fields
        enriched = {
            "model_file": model_filename,
            "model_path": model_path,
            "file_hash": self._compute_file_hash(model_path)
            if os.path.exists(model_path)
            else None,
            "file_size_bytes": os.path.getsize(model_path)
            if os.path.exists(model_path)
            else 0,
            "created_at": time.time(),
            "created_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            **metadata,
        }

        # Merge with existing metadata if present
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Preserve version history
            if "version_history" not in enriched:
                enriched["version_history"] = existing.get("version_history", [])
            enriched["version_history"].append(
                {
                    "version": len(enriched["version_history"]) + 1,
                    "previous_hash": existing.get("file_hash"),
                    "previous_timesteps": existing.get("timesteps"),
                    "updated_at": time.time(),
                }
            )

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(enriched, f, indent=2, ensure_ascii=False)

        return meta_path

    def load(self, model_filename: str) -> Optional[dict]:
        """Load metadata for a model file. Returns None if not found."""
        meta_path = self._meta_path(model_filename)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def validate(self, model_filename: str) -> bool:
        """Validate that model file matches its metadata.

        Checks:
        1. Metadata file exists
        2. Model file exists
        3. File hash matches (first 64KB)
        4. Observation dimension matches current OBS_DIM
        """
        meta = self.load(model_filename)
        if meta is None:
            return False

        model_path = self._model_path(model_filename)
        if not os.path.exists(model_path):
            return False

        # Verify file hash
        current_hash = self._compute_file_hash(model_path)
        stored_hash = meta.get("file_hash")
        if stored_hash and current_hash != stored_hash:
            print(
                f"[Metadata] Hash mismatch: {model_filename} "
                f"(expected {stored_hash}, got {current_hash})"
            )
            return False

        # Verify observation dimension if specified
        if "obs_dim" in meta:
            try:
                from deep_rl.pmtec_env import OBS_DIM

                if meta["obs_dim"] != OBS_DIM:
                    print(
                        f"[Metadata] Obs dim mismatch: {model_filename} "
                        f"(model={meta['obs_dim']}, env={OBS_DIM})"
                    )
                    return False
            except ImportError:
                pass

        return True

    def list_all(self) -> list:
        """List all models with their metadata status."""
        results = []
        if not os.path.exists(self._model_dir):
            return results

        for f in sorted(os.listdir(self._model_dir)):
            if f.endswith((".zip", ".pt", ".pth")):
                meta = self.load(f)
                results.append(
                    {
                        "model_file": f,
                        "has_metadata": meta is not None,
                        "algorithm": meta.get("algorithm") if meta else None,
                        "timesteps": meta.get("timesteps") if meta else None,
                        "obs_dim": meta.get("obs_dim") if meta else None,
                        "created_at": meta.get("created_at_iso") if meta else None,
                        "valid": self.validate(f) if meta else False,
                    }
                )
        return results

    def generate_for_all_existing(self) -> int:
        """Generate metadata for all model files that don't have it yet.

        Returns count of newly created metadata files.
        """
        # Known model configs
        model_configs = {
            "pmtec_dqn_p7_v2.zip": {
                "algorithm": "DQN",
                "library": "stable_baselines3",
                "timesteps": 200000,
                "obs_dim": 182,
                "n_actions": 6,
                "policy_arch": [128, 64],
                "activation": "ReLU",
                "training_type": "curriculum_learning",
                "evaluation": {
                    "stealth_intercept_rate": 0.791,
                    "overall_intercept_rate": 0.762,
                    "ci_95": [0.747, 0.777],
                },
                "notes": "P7-v2 production model. Curriculum learning with 3 stages.",
            },
            "pmtec_dqn_p7.zip": {
                "algorithm": "DQN",
                "library": "stable_baselines3",
                "timesteps": 200000,
                "obs_dim": 182,
                "n_actions": 6,
                "training_type": "curriculum_learning",
                "evaluation": {
                    "stealth_intercept_rate": 0.545,
                    "notes": "P7-v1: did not meet 70% target (env physics constraint)",
                },
                "notes": "P7-v1 intermediate model. Superseded by P7-v2.",
            },
            "pmtec_dqn_p6.zip": {
                "algorithm": "DQN",
                "library": "stable_baselines3",
                "timesteps": 200000,
                "obs_dim": 182,
                "n_actions": 6,
                "policy_arch": [128, 64],
                "training_type": "xpu_accelerated",
                "evaluation": {
                    "overall_intercept_rate": 0.762,
                    "stealth_intercept_rate": 0.537,
                },
                "notes": "P6 production model. 182-dim observation space.",
            },
            "pmtec_iql_intercept.zip": {
                "algorithm": "IQL",
                "library": "stable_baselines3",
                "timesteps": 6000,
                "obs_dim": 182,
                "n_actions": 3,
                "agent_role": "intercept",
                "notes": "P8 IQL intercept agent. 182-dim retrained.",
            },
            "pmtec_iql_dispersal.zip": {
                "algorithm": "IQL",
                "library": "stable_baselines3",
                "timesteps": 6000,
                "obs_dim": 182,
                "n_actions": 3,
                "agent_role": "dispersal",
                "notes": "P8 IQL dispersal agent. 182-dim retrained.",
            },
            "pmtec_maddpg_intercept.pt": {
                "algorithm": "MADDPG",
                "library": "pytorch",
                "timesteps": 6000,
                "obs_dim": 182,
                "n_actions": 3,
                "agent_role": "intercept",
                "architecture": "Actor-Critic (centralized critic)",
                "notes": "P8 MADDPG intercept actor. 182-dim retrained.",
            },
            "pmtec_maddpg_dispersal.pt": {
                "algorithm": "MADDPG",
                "library": "pytorch",
                "timesteps": 6000,
                "obs_dim": 182,
                "n_actions": 3,
                "agent_role": "dispersal",
                "architecture": "Actor-Critic (centralized critic)",
                "notes": "P8 MADDPG dispersal actor. 182-dim retrained.",
            },
        }

        count = 0
        for model_file, cfg in model_configs.items():
            model_path = self._model_path(model_file)
            if not os.path.exists(model_path):
                continue
            meta = self.load(model_file)
            if meta is None:
                self.write(model_file, cfg)
                count += 1
                print(f"[Metadata] Created: {model_file}")

        return count


if __name__ == "__main__":
    mgr = ModelMetadataManager()

    # Generate metadata for all existing models
    n = mgr.generate_for_all_existing()
    print(f"\nGenerated metadata for {n} models")

    # List all
    print("\nModel Inventory:")
    print("-" * 80)
    for m in mgr.list_all():
        status = (
            "VALID"
            if m["valid"]
            else ("NOMETA" if not m["has_metadata"] else "INVALID")
        )
        print(
            f"  [{status}] {m['model_file']:40s} "
            f"algo={m['algorithm'] or '?':8s} "
            f"steps={m['timesteps'] or '?':>8} "
            f"obs={m['obs_dim'] or '?':>4} "
            f"created={m['created_at'] or '?'}"
        )
    print("-" * 80)
