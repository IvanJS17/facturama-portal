from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.services.csd_parser import parse_csd_certificate


def _build_cer(rfc: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Acme SA de CV"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, rfc),
            x509.NameAttribute(NameOID.COMMON_NAME, "Acme CSD"),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(12345678901234567890)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_parse_csd_certificate_extracts_metadata():
    rfc = "AAA010101AAA"
    metadata = parse_csd_certificate(_build_cer(rfc))

    assert metadata["rfc"] == rfc
    assert metadata["serial"]
    assert metadata["subject"]
    assert metadata["valid_from"]
    assert metadata["valid_to"]
