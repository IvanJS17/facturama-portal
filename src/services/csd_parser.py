"""CSD (.cer) parsing utilities."""

from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID


class CSDParserError(ValueError):
    """Raised when a CSD certificate cannot be parsed."""


def parse_csd_certificate(certificate_bytes: bytes) -> dict[str, str]:
    if not certificate_bytes:
        raise CSDParserError("El archivo .cer esta vacio")

    try:
        cert = x509.load_der_x509_certificate(certificate_bytes)
    except ValueError:
        try:
            cert = x509.load_pem_x509_certificate(certificate_bytes)
        except ValueError as exc:
            raise CSDParserError("No se pudo leer el certificado .cer") from exc

    rfc = ""
    for attr in cert.subject:
        if attr.oid == NameOID.ORGANIZATIONAL_UNIT_NAME and attr.value:
            rfc = attr.value.strip().upper()
            break

    serial = format(cert.serial_number, "X")
    subject = cert.subject.rfc4514_string()
    valid_from = cert.not_valid_before_utc.isoformat()
    valid_to = cert.not_valid_after_utc.isoformat()

    return {
        "rfc": rfc,
        "serial": serial,
        "subject": subject,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }
