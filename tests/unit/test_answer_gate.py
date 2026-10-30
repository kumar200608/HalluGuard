"""Unit tests for the FinalAnswerGate — no LLM, no network."""
import pytest

from app.core.enums import (
    ClaimType,
    GateDecision,
    HallucinationRisk,
    VerificationStatus,
)
from app.models.schemas import Claim, ClaimVerificationResult
from app.services.answer_gate import FinalAnswerGate


gate = FinalAnswerGate()


def _result(
    status: VerificationStatus,
    risk: HallucinationRisk = HallucinationRisk.MEDIUM,
    fake_citation: bool = False,
    requires_evidence: bool = True,
    temporal_sensitive: bool = False,
    temporal_valid: bool | None = None,
) -> ClaimVerificationResult:
    claim = Claim(
        text="test claim",
        claim_type=ClaimType.FACT,
        risk_level=risk,
        requires_external_evidence=requires_evidence,
        temporal_sensitive=temporal_sensitive,
    )
    r = ClaimVerificationResult(claim=claim, status=status)
    r.fake_citation_detected = fake_citation
    r.temporal_valid = temporal_valid
    return r


class TestFinalAnswerGate:
    def test_all_verified_allows(self):
        results = [
            _result(VerificationStatus.VERIFIED),
            _result(VerificationStatus.VERIFIED),
        ]
        decision = gate.evaluate(results, HallucinationRisk.LOW)
        assert decision == GateDecision.ALLOW

    def test_fake_citation_blocks(self):
        results = [_result(VerificationStatus.VERIFIED, fake_citation=True)]
        decision = gate.evaluate(results, HallucinationRisk.HIGH)
        assert decision == GateDecision.BLOCK_AND_REGENERATE

    def test_critical_risk_blocks(self):
        results = [_result(VerificationStatus.PARTIALLY_VERIFIED)]
        decision = gate.evaluate(results, HallucinationRisk.CRITICAL)
        assert decision == GateDecision.BLOCK_AND_REGENERATE

    def test_high_risk_unsupported_blocks(self):
        results = [
            _result(VerificationStatus.UNSUPPORTED, risk=HallucinationRisk.HIGH),
        ]
        decision = gate.evaluate(results, HallucinationRisk.HIGH)
        assert decision == GateDecision.BLOCK_AND_REGENERATE

    def test_minor_unsupported_rewrites(self):
        results = [
            _result(VerificationStatus.VERIFIED, risk=HallucinationRisk.HIGH),
            _result(VerificationStatus.UNSUPPORTED, risk=HallucinationRisk.LOW),
        ]
        decision = gate.evaluate(results, HallucinationRisk.MEDIUM)
        assert decision in (GateDecision.REWRITE, GateDecision.BLOCK_AND_REGENERATE)

    def test_contradicted_high_risk_conflict_disclosure(self):
        results = [
            _result(VerificationStatus.CONTRADICTED, risk=HallucinationRisk.HIGH),
            _result(VerificationStatus.UNSUPPORTED, risk=HallucinationRisk.HIGH),
        ]
        decision = gate.evaluate(results, HallucinationRisk.HIGH)
        assert decision in (
            GateDecision.REGENERATE_WITH_CONFLICT_DISCLOSURE,
            GateDecision.BLOCK_AND_REGENERATE,
        )

    def test_verification_unavailable_returns_uncertain(self):
        results = [
            _result(VerificationStatus.VERIFICATION_UNAVAILABLE, risk=HallucinationRisk.MEDIUM),
        ]
        decision = gate.evaluate(results, HallucinationRisk.MEDIUM)
        assert decision in (
            GateDecision.RETURN_UNCERTAIN_ANSWER,
            GateDecision.REWRITE,
            GateDecision.BLOCK_AND_REGENERATE,
        )

    def test_no_evidence_required_allows(self):
        results = [
            _result(VerificationStatus.VERIFIED, requires_evidence=False),
        ]
        decision = gate.evaluate(results, HallucinationRisk.LOW)
        assert decision == GateDecision.ALLOW
