import pytest

from src.utils.fiscal import normalize_postal_code, normalize_rfc, normalize_legal_name


def test_normalize_rfc_trims_uppercases_and_validates_shape():
    assert normalize_rfc(" cosc8001137na ") == "COSC8001137NA"


@pytest.mark.parametrize("bad_rfc", ["", "ABC123", "INVALID-RFC", "TOO-LONG010101AAAA"])
def test_normalize_rfc_rejects_invalid_values(bad_rfc):
    with pytest.raises(ValueError, match="RFC"):
        normalize_rfc(bad_rfc)


def test_normalize_postal_code_keeps_five_digits():
    assert normalize_postal_code(" 01000 ") == "01000"


@pytest.mark.parametrize("bad_cp", ["", "1234", "123456", "12A45"])
def test_normalize_postal_code_rejects_invalid_values(bad_cp):
    with pytest.raises(ValueError, match="postal code"):
        normalize_postal_code(bad_cp)


def test_normalize_legal_name_trims_collapses_spaces_and_uppercases():
    assert normalize_legal_name("  Acme   de Mexico, sa de cv ") == "ACME DE MEXICO, SA DE CV"


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_normalize_legal_name_rejects_blank_values(bad_name):
    with pytest.raises(ValueError, match="name"):
        normalize_legal_name(bad_name)
