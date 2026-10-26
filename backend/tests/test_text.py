"""Normalização de telefone e placa — casos reais do balcão."""

import pytest

from app.core.text import normalize_placa, normalize_telefone, placa_fragment


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("(82) 99911-0001", "5582999110001"),
        ("82 3333-1234", "558233331234"),
        ("+55 82 99911-0002", "5582999110002"),
        ("00 55 82 99911-0001", "5582999110001"),
        ("082 99911-0001", "5582999110001"),  # 0 do DDD
        ("0 21 82 99911-0001", "5582999110001"),  # 0 + operadora + DDD
        ("+1 (305) 555-0123", "13055550123"),  # internacional preservado
        ("+351 912 345 678", "351912345678"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_telefone_ok(entrada, esperado):
    assert normalize_telefone(entrada) == esperado


@pytest.mark.parametrize("entrada", ["123", "0800 123 4567", "4004-1234", "99911", "+0 12 3456", "1234567890123456"])
def test_normalize_telefone_rejeita(entrada):
    with pytest.raises(ValueError):
        normalize_telefone(entrada)


@pytest.mark.parametrize(
    "entrada,esperado",
    [("bra-2e19", "BRA2E19"), ("ABC 1234", "ABC1234"), ("abc1d23", "ABC1D23"), ("", None), ("  ", None), (None, None)],
)
def test_normalize_placa_ok(entrada, esperado):
    assert normalize_placa(entrada) == esperado


@pytest.mark.parametrize("entrada", ["ABCD12345", "AÇB1234", "ÑAB1234"])
def test_normalize_placa_rejeita(entrada):
    with pytest.raises(ValueError):
        normalize_placa(entrada)


def test_placa_fragment_never_raises():
    assert placa_fragment("Corolla XEi") is None
    assert placa_fragment("2e1") == "2E1"
    assert placa_fragment("bra-2e19") == "BRA2E19"
    assert placa_fragment("") is None
    assert placa_fragment("Hilux SRX") is None
