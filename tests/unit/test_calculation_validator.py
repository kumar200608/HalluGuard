"""Unit tests for CalculationValidator — fully deterministic, no network."""
import pytest

from app.core.enums import ClaimType, HallucinationRisk
from app.models.schemas import Claim
from app.services.calculation_validator import CalculationValidator, safe_eval

cv = CalculationValidator()


def make_claim(text: str) -> Claim:
    return Claim(
        text=text,
        claim_type=ClaimType.CALCULATION,
        numeric=True,
        risk_level=HallucinationRisk.MEDIUM,
    )


class TestSafeEval:
    def test_addition(self):
        assert safe_eval("2 + 2") == 4

    def test_multiplication(self):
        assert safe_eval("17 * 23") == 391

    def test_percentage(self):
        assert abs(safe_eval("20/100 * 500") - 100.0) < 1e-9

    def test_power(self):
        assert safe_eval("2 ** 10") == 1024

    def test_nested(self):
        assert safe_eval("(10 + 5) * 2") == 30

    def test_rejects_builtins(self):
        with pytest.raises((ValueError, AttributeError)):
            safe_eval("__import__('os').system('ls')")

    def test_rejects_strings(self):
        with pytest.raises((ValueError, TypeError)):
            safe_eval("'hello'")


class TestCalculationValidator:
    def test_correct_calculation(self):
        claim = make_claim("20% of 500 = 100")
        ok, msg = cv.validate(claim)
        assert ok is True

    def test_incorrect_calculation(self):
        """The infamous '20% of 500 = 150' hallucination."""
        claim = make_claim("20% of 500 = 150")
        ok, msg = cv.validate(claim)
        assert ok is False
        assert "150" in msg or "100" in msg, f"Expected value in msg, got: {msg}"

    def test_multiplication_correct(self):
        claim = make_claim("17 × 23 = 391")
        ok, msg = cv.validate(claim)
        assert ok is True

    def test_multiplication_wrong(self):
        claim = make_claim("17 × 23 = 400")
        ok, msg = cv.validate(claim)
        assert ok is False

    def test_no_expression(self):
        claim = make_claim("Python is a programming language")
        ok, msg = cv.validate(claim)
        assert ok is None
