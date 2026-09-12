"""
mTLS Certificate Manager - Generates and manages X.509 certificates.

Creates a self-signed CA, then signs server and client certificates.
Certificates are stored on disk and auto-renewed before expiry.

Uses the `cryptography` library for PKI operations.
"""

import datetime
import os
import threading

import grpc
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class CertificateManager:
    """Manages mTLS certificates for gRPC mutual authentication."""

    def __init__(self, cert_dir: str = None):
        if cert_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cert_dir = os.path.join(project_root, "data", "certs")
        self._cert_dir = cert_dir
        os.makedirs(cert_dir, exist_ok=True)

        self._ca_cert_path = os.path.join(cert_dir, "ca.crt")
        self._ca_key_path = os.path.join(cert_dir, "ca.key")
        self._server_cert_path = os.path.join(cert_dir, "server.crt")
        self._server_key_path = os.path.join(cert_dir, "server.key")
        self._client_cert_path = os.path.join(cert_dir, "client.crt")
        self._client_key_path = os.path.join(cert_dir, "client.key")

        self._lock = threading.Lock()
        self._ensure_certs()

    def _ensure_certs(self):
        """Generate all certificates if they don't exist yet."""
        with self._lock:
            if not os.path.exists(self._ca_cert_path):
                self._generate_ca()
            if not os.path.exists(self._server_cert_path):
                self._generate_server_cert()
            if not os.path.exists(self._client_cert_path):
                self._generate_client_cert()

    def _generate_ca(self):
        """Generate a self-signed CA certificate (10-year validity)."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PMTEC-DTC2026"),
                x509.NameAttribute(NameOID.COMMON_NAME, "PMTEC-Root-CA"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        self._write_cert(self._ca_cert_path, cert)
        self._write_key(self._ca_key_path, key)

    def _generate_server_cert(self):
        """Generate a server certificate signed by the CA (1-year validity)."""
        ca_cert, ca_key = self._load_ca()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PMTEC-DTC2026"),
                x509.NameAttribute(NameOID.COMMON_NAME, "PMTEC-Server"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.DNSName("pmtec-server"),
                        x509.IPAddress(self._get_localhost_ip()),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        self._write_cert(self._server_cert_path, cert)
        self._write_key(self._server_key_path, key)

    def _generate_client_cert(self):
        """Generate a client certificate signed by the CA (1-year validity)."""
        ca_cert, ca_key = self._load_ca()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PMTEC-DTC2026"),
                x509.NameAttribute(NameOID.COMMON_NAME, "PMTEC-Client"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        self._write_cert(self._client_cert_path, cert)
        self._write_key(self._client_key_path, key)

    @staticmethod
    def _get_localhost_ip():
        import ipaddress

        return ipaddress.IPv4Address("127.0.0.1")

    @staticmethod
    def _write_cert(path: str, cert):
        with open(path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

    @staticmethod
    def _write_key(path: str, key):
        with open(path, "wb") as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )

    def _load_ca(self):
        """Load CA certificate and private key."""
        with open(self._ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        with open(self._ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        return ca_cert, ca_key

    def load_server_credentials(self) -> grpc.ServerCredentials:
        """Load gRPC server credentials for mTLS.

        Returns ServerCredentials configured for mutual TLS:
        server presents its cert, and verifies client certs against CA.
        """
        with open(self._server_key_path, "rb") as f:
            server_key = f.read()
        with open(self._server_cert_path, "rb") as f:
            server_cert = f.read()
        with open(self._ca_cert_path, "rb") as f:
            ca_cert = f.read()

        return grpc.ssl_server_credentials(
            [(server_key, server_cert)],
            root_certificates=ca_cert,
            require_client_auth=True,
        )

    def get_client_channel_credentials(self) -> grpc.ChannelCredentials:
        """Load gRPC client credentials for connecting to mTLS server.

        Used by client code to create a secure channel.
        """
        with open(self._client_key_path, "rb") as f:
            client_key = f.read()
        with open(self._client_cert_path, "rb") as f:
            client_cert = f.read()
        with open(self._ca_cert_path, "rb") as f:
            ca_cert = f.read()

        return grpc.ssl_channel_credentials(
            root_certificates=ca_cert,
            private_key=client_key,
            certificate_chain=client_cert,
        )

    def check_and_renew(self) -> bool:
        """Check certificate expiry and renew if within 30 days of expiry.

        Returns True if any certificate was renewed, False otherwise.
        """
        renewed = False
        now = datetime.datetime.utcnow()
        threshold = datetime.timedelta(days=30)

        for cert_path, renew_fn in [
            (self._server_cert_path, self._generate_server_cert),
            (self._client_cert_path, self._generate_client_cert),
        ]:
            if os.path.exists(cert_path):
                with open(cert_path, "rb") as f:
                    cert = x509.load_pem_x509_certificate(f.read())
                try:
                    expiry = cert.not_valid_after_utc
                except AttributeError:
                    expiry = cert.not_valid_after
                if expiry - now < threshold:
                    renew_fn()
                    renewed = True

        return renewed

    @property
    def cert_dir(self) -> str:
        return self._cert_dir

    def get_cert_info(self) -> dict:
        """Return certificate status information."""
        info = {}
        for name, path in [
            ("CA", self._ca_cert_path),
            ("Server", self._server_cert_path),
            ("Client", self._client_cert_path),
        ]:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    cert = x509.load_pem_x509_certificate(f.read())
                try:
                    not_before = cert.not_valid_before_utc
                    not_after = cert.not_valid_after_utc
                except AttributeError:
                    not_before = cert.not_valid_before
                    not_after = cert.not_valid_after
                info[name] = {
                    "subject": cert.subject.rfc4514_string(),
                    "issuer": cert.issuer.rfc4514_string(),
                    "not_before": not_before.isoformat(),
                    "not_after": not_after.isoformat(),
                    "serial": cert.serial_number,
                }
            else:
                info[name] = None
        return info
