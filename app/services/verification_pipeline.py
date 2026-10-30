"""Verification Pipeline Orchestrator.

Coordinates all components end-to-end:
  ClaimExtractor → EvidenceRetriever → EntailmentChecker →
  ContradictionDetector → TemporalValidator → CalculationValidator →
  CitationValidator → ConfidenceEngine → RiskEngine →
  AnswerRepairer → FinalAnswerGate

This is the component the host agent calls via verify_answer().
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.core.config import settings
from app.core.enums import (
    ClaimType,
    EntailmentResult,
    GateDecision,
    HallucinationRisk,
    VerificationMode,
    VerificationStatus,
    SKIP_VERIFICATION_TYPES,
)
from app.models.schemas import (
    Claim,
    ClaimVerificationResult,
    VerificationReport,
    VerificationRequest,
    VerificationResponse,
)
from app.security.guards import detect_injection, sanitize_query, wrap_untrusted
from app.services.answer_gate import answer_gate
from app.services.answer_repairer import answer_repairer
from app.services.calculation_validator import calculation_validator
from app.services.citation_validator import citation_validator
from app.services.claim_extractor import claim_extractor
from app.services.confidence_engine import compute_confidence, determine_verification_status, risk_engine
from app.services.contradiction_detector import contradiction_detector
from app.services.entailment_checker import entailment_checker
from app.services.evidence_retriever import evidence_retriever
from app.services.temporal_validator import temporal_validator

logger = logging.getLogger(__name__)

_UNCERTAIN_TEMPLATE = (
    "I was unable to obtain sufficient verified evidence to answer this confidently. "
    "Here is what I can confirm: {confirmed}. "
    "The following claims could not be verified: {unverified}."
)

_CONFLICT_TEMPLATE = (
    "Sources disagree on the following: {conflicts}. "
    "I cannot state a single definitive answer without further verification. "
    "Verified information: {confirmed}."
)


class VerificationPipeline:
    """Full hallucination prevention pipeline."""

    async def run(self, request: VerificationRequest) -> VerificationResponse:
        request.query = sanitize_query(request.query)
        request.answer = sanitize_query(request.answer)

        logger.info("[%s] Starting verification pipeline", request.request_id)

        # Detect injection in the query itself
        injections = detect_injection(request.query + " " + request.answer)
        if injections:
            logger.warning("[%s] Possible injection in input: %s", request.request_id, injections)

        # Phase 1: Extract claims
        claims = await claim_extractor.extract(
            query=request.query,
            answer=request.answer,
            context=request.context or "",
        )

        # Phase 2: Verify each claim
        results = await self._verify_claims(claims, request)

        # Phase 3: Risk assessment
        risk_score, risk_level = risk_engine.compute(results)

        # Phase 4: Gate decision
        decision = answer_gate.evaluate(results, risk_level)

        # Phase 5: Construct answer
        verified_answer, warnings = await self._build_answer(
            request, results, decision, risk_score, risk_level
        )

        # Phase 6: Collect validated citations
        citations = [
            e.source
            for r in results
            for e in r.evidence
            if e.entailment in (EntailmentResult.SUPPORTS, EntailmentResult.PARTIALLY_SUPPORTS)
        ]
        # Deduplicate citations by URL
        seen_urls: set[str] = set()
        unique_citations = []
        for c in citations:
            if c.url not in seen_urls:
                seen_urls.add(c.url)
                unique_citations.append(c)

        overall_status = self._overall_status(results)

        report = VerificationReport(
            request_id=request.request_id,
            query=request.query,
            original_answer=request.answer,
            verified_answer=verified_answer,
            claims=results,
            overall_status=overall_status,
            gate_decision=decision,
            hallucination_risk=risk_level,
            risk_score=risk_score,
            citations=unique_citations,
            warnings=warnings,
            debug_info=self._build_debug(results, claims) if request.debug else None,
        )

        allowed = decision == GateDecision.ALLOW
        logger.info(
            "[%s] Pipeline complete: gate=%s risk=%s verified=%d/%d",
            request.request_id, decision.value, risk_level.value,
            sum(1 for r in results if r.status == VerificationStatus.VERIFIED),
            len(results),
        )

        return VerificationResponse(
            allowed=allowed,
            answer=verified_answer,
            verification_report=report,
        )

    # ------------------------------------------------------------------
    # Claim verification
    # ------------------------------------------------------------------

    async def _verify_claims(
        self,
        claims: list[Claim],
        request: VerificationRequest,
    ) -> list[ClaimVerificationResult]:
        tasks = [self._verify_single(claim, request) for claim in claims]
        return await asyncio.gather(*tasks)

    async def _verify_single(
        self,
        claim: Claim,
        request: VerificationRequest,
    ) -> ClaimVerificationResult:
        result = ClaimVerificationResult(claim=claim)

        # Skip verification for non-factual types
        if claim.claim_type in SKIP_VERIFICATION_TYPES:
            result.status = VerificationStatus(claim.claim_type.value)
            result.confidence = 0.5
            return result

        # Calculation check (deterministic — no LLM or network needed)
        if claim.numeric or claim.claim_type == ClaimType.CALCULATION:
            calc_ok, calc_msg = calculation_validator.validate(claim)
            result.calculation_verified = calc_ok
            if calc_ok is False:
                result.status = VerificationStatus.CONTRADICTED
                result.repair_instruction = calc_msg
                result.confidence = 0.0
                return result

        # Citation validation for any URLs in the claim
        if not claim.requires_external_evidence:
            result.status = VerificationStatus.VERIFIED
            result.confidence = 0.9
            return result

        # Skip evidence retrieval in FAST mode for low-risk claims
        if (
            request.mode == VerificationMode.FAST
            and claim.risk_level == HallucinationRisk.LOW
        ):
            result.status = VerificationStatus.UNVERIFIABLE
            result.confidence = 0.5
            return result

        # Retrieve evidence
        try:
            chunks = await evidence_retriever.retrieve(claim)
        except Exception as exc:
            logger.error("Evidence retrieval error: %s", exc)
            result.status = VerificationStatus.VERIFICATION_UNAVAILABLE
            return result

        if not chunks:
            result.status = VerificationStatus.UNSUPPORTED
            result.repair_instruction = f"No evidence found for: '{claim.text}'"
            return result

        # Wrap external content before entailment (prompt injection defense)
        for chunk in chunks:
            chunk.text = wrap_untrusted(chunk.text, chunk.source.url)

        # Entailment checking
        chunks = await entailment_checker.check_batch(claim, chunks)

        # Split into supporting / contradicting
        supporting = [c for c in chunks if c.entailment in (EntailmentResult.SUPPORTS, EntailmentResult.PARTIALLY_SUPPORTS)]
        contradicting = [c for c in chunks if c.entailment == EntailmentResult.CONTRADICTS]

        # Citation validation
        fake_cit, cit_warnings = await citation_validator.validate_claim_citations(claim)
        result.fake_citation_detected = fake_cit

        # Temporal validation
        temporal_valid, temporal_warnings = temporal_validator.validate_claim_temporality(
            claim, chunks, request.query
        )
        result.temporal_valid = temporal_valid

        # Contradiction detection
        conflict = contradiction_detector.detect(supporting, contradicting)
        if conflict.conflict_detected:
            result.contradictions = contradicting

        # Confidence score
        confidence = compute_confidence(
            chunks=chunks,
            temporal_valid=temporal_valid,
            fake_citation=fake_cit,
            calculation_verified=result.calculation_verified,
        )
        result.confidence = confidence
        result.evidence = supporting or chunks[:3]

        # Verification status
        result.status = determine_verification_status(
            chunks=chunks,
            confidence=confidence,
            fake_citation=fake_cit,
            requires_evidence=claim.requires_external_evidence,
            calculation_verified=result.calculation_verified,
        )

        # Set repair instruction
        if result.status not in (VerificationStatus.VERIFIED,):
            result.repair_instruction = self._repair_instruction(result.status, claim, cit_warnings + temporal_warnings)

        return result

    # ------------------------------------------------------------------
    # Answer construction
    # ------------------------------------------------------------------

    async def _build_answer(
        self,
        request: VerificationRequest,
        results: list[ClaimVerificationResult],
        decision: GateDecision,
        risk_score: float,
        risk_level: HallucinationRisk,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []

        if decision == GateDecision.ALLOW:
            return request.answer, warnings

        if decision == GateDecision.RETURN_UNCERTAIN_ANSWER:
            confirmed = ", ".join(
                f'"{r.claim.text}"'
                for r in results
                if r.status == VerificationStatus.VERIFIED
            ) or "none"
            unverified = ", ".join(
                f'"{r.claim.text}"'
                for r in results
                if r.status in (VerificationStatus.UNSUPPORTED, VerificationStatus.UNVERIFIABLE)
            ) or "none"
            answer = _UNCERTAIN_TEMPLATE.format(confirmed=confirmed, unverified=unverified)
            warnings.append("Verification was unavailable or insufficient for key claims.")
            return answer, warnings

        if decision == GateDecision.REGENERATE_WITH_CONFLICT_DISCLOSURE:
            conflicts = ", ".join(
                f'"{r.claim.text}"'
                for r in results
                if r.status == VerificationStatus.CONTRADICTED
            )
            confirmed = ", ".join(
                f'"{r.claim.text}"'
                for r in results
                if r.status == VerificationStatus.VERIFIED
            ) or "none"
            answer = _CONFLICT_TEMPLATE.format(conflicts=conflicts, confirmed=confirmed)
            warnings.append("Evidence conflicts were detected. See claims for details.")
            return answer, warnings

        # REWRITE or BLOCK_AND_REGENERATE → repair
        repaired, changes = await answer_repairer.repair(request.answer, results)
        if changes:
            warnings.append(f"Answer was repaired: {len(changes)} claim(s) corrected.")
        return repaired, warnings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _overall_status(results: list[ClaimVerificationResult]) -> VerificationStatus:
        if not results:
            return VerificationStatus.UNVERIFIABLE
        statuses = {r.status for r in results}
        if statuses == {VerificationStatus.VERIFIED}:
            return VerificationStatus.VERIFIED
        if VerificationStatus.CONTRADICTED in statuses:
            return VerificationStatus.CONTRADICTED
        if VerificationStatus.UNSUPPORTED in statuses:
            return VerificationStatus.UNSUPPORTED
        return VerificationStatus.PARTIALLY_VERIFIED

    @staticmethod
    def _repair_instruction(status: VerificationStatus, claim: Claim, extra: list[str]) -> str:
        base = {
            VerificationStatus.UNSUPPORTED: f"No reliable source found for '{claim.text}'. Remove or explicitly state unverified.",
            VerificationStatus.CONTRADICTED: f"Evidence contradicts '{claim.text}'. Remove or disclose contradiction.",
            VerificationStatus.PARTIALLY_VERIFIED: f"Only partial evidence for '{claim.text}'. Qualify with uncertainty language.",
            VerificationStatus.UNVERIFIABLE: f"'{claim.text}' cannot be verified. Label as unverifiable.",
        }.get(status, f"Review claim: '{claim.text}'")
        if extra:
            base += " Additional: " + "; ".join(extra[:3])
        return base

    @staticmethod
    def _build_debug(
        results: list[ClaimVerificationResult],
        claims: list[Claim],
    ) -> dict:
        return {
            "total_claims": len(claims),
            "per_claim": [
                {
                    "id": r.claim.id,
                    "text": r.claim.text,
                    "type": r.claim.claim_type.value,
                    "status": r.status.value,
                    "confidence": r.confidence,
                    "sources": [e.source.url for e in r.evidence[:3]],
                    "fake_citation": r.fake_citation_detected,
                    "temporal_valid": r.temporal_valid,
                    "repair": r.repair_instruction,
                }
                for r in results
            ],
        }


pipeline = VerificationPipeline()


async def verify_answer(
    query: str,
    answer: str,
    context: str | None = None,
    mode: str = "standard",
    debug: bool = False,
) -> VerificationResponse:
    """
    Primary plugin entry point.
    The host agent calls this before returning any answer to the user.

    Example:
        response = await verify_answer(query=user_query, answer=draft_answer)
        if response.allowed:
            return response.answer
        else:
            # Use the repaired answer
            return response.answer
    """
    req = VerificationRequest(
        query=query,
        answer=answer,
        context=context,
        mode=VerificationMode(mode),
        debug=debug,
    )
    return await pipeline.run(req)
