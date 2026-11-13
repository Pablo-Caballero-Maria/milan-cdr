import pytest

from milan_cdr.countries import country_name, lookup


@pytest.mark.parametrize(
    ("code", "name"),
    [
        (39, "Italia"),
        (33, "Francia"),
        (34, "España"),
        (44, "Reino Unido"),
        (49, "Alemania"),
        (86, "China"),
        (1, "Estados Unidos"),
        (7, "Rusia"),
        (1204, "Canadá"),
        (1809, "República Dominicana"),
        (7701, "Kazajistán"),
    ],
)
def test_known_codes(code, name):
    assert country_name(code) == name


def test_unknown_and_unassigned():
    assert lookup(0).region is None
    assert "Desconocido" in lookup(0).name
    assert lookup(999).region is None


def test_non_geographic():
    assert lookup(882).region == "001"


def test_is_foreign():
    assert not lookup(39).is_foreign
    assert not lookup(0).is_foreign
    assert lookup(33).is_foreign
