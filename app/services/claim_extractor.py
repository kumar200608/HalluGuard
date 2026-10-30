"""Claim Extraction Service.

Sends the agent's draft answer to an LLM with a structured prompt and
returns a list of independently-verifiable Claim objects.
"""
from __future__ import annotations

import json
import logging
import re

from app.core.enums import (
    ClaimType,
    HallucinationRisk,
    HIGH_RISK_CLAIM_TYPES,
    SKIP_VERIFICATION_TYPES,
)
from app.models.schemas import Claim
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """You are a rigorous fact-extraction engine.
Your ONLY job is to decompose an AI-generated answer into atomic, independently-verifiable factual claims.

Rules:
1. Each claim must be a single, self-contained statement.
2. Do NOT combine multiple facts into one claim.
3. Do NOT treat an entire paragraph as one claim.
4. Classify every claim with one of these types:
   FACT | DATE | NUMBER | STATISTIC | PERSON | ORGANIZATION | PRODUCT | LOCATION | EVENT |
   TECHNICAL_SPECIFICATION | API_BEHAVIOR | LEGAL_CLAIM | MEDICAL_CLAIM | FINANCIAL_CLAIM |
   POLITICAL_CLAIM | CURRENT_STATUS | HISTORICAL_CLAIM | QUOTE | SOURCE_REFERENCE |
   CALCULATION | INFERENCE | OPINION | USER_PROVIDED | COMMON_KNOWLEDGE
5. Mark temporal_sensitive=true for any claim about current state, prices, versions, availability.
6. Mark numeric=true for any claim containing numbers, percentages, dates, or measurements.
7. Mark high_risk_domain=true for medical, legal, financial, or political claims.
8. Return ONLY valid JSON — no prose, no markdown fences.

Output format:
{
  "claims": [
    {
      "text": "<atomic claim text>",
      "claim_type": "<TYPE>",
      "temporal_sensitive": false,
      "numeric": false,
      "high_risk_domain": false,
      "version_sensitive": false
    }
  ]
}"""


_EXTRACT_USER = """User query: {query}

Agent answer to decompose:
{answer}

Context (if any): {context}

Extract all atomic factual claims from the agent answer."""


# Claim types that never need external evidence
_NO_EVIDENCE_TYPES = {
    ClaimType.COMMON_KNOWLEDGE,
    ClaimType.USER_PROVIDED,
    ClaimType.OPINION,
    ClaimType.INFERENCE,
    ClaimType.CALCULATION,
}


def _assess_risk(claim_type: ClaimType, numeric: bool, high_risk_domain: bool, temporal_sensitive: bool) -> HallucinationRisk:
    if high_risk_domain or claim_type in HIGH_RISK_CLAIM_TYPES:
        return HallucinationRisk.HIGH
    if numeric or temporal_sensitive:
        return HallucinationRisk.MEDIUM
    if claim_type in SKIP_VERIFICATION_TYPES:
        return HallucinationRisk.LOW
    return HallucinationRisk.MEDIUM


class ClaimExtractor:
    """Extract and classify atomic claims from an agent answer."""

    async def extract(self, query: str, answer: str, context: str = "") -> list[Claim]:
        prompt = _EXTRACT_USER.format(query=query, answer=answer, context=context or "none")
        try:
            raw = await llm_client.complete(system=_EXTRACT_SYSTEM, user=prompt)
            data = self._parse_json(raw)
        except Exception as exc:
            logger.error("Claim extraction failed: %s", exc)
            # Fallback: treat entire answer as one unclassified fact
            return [Claim(text=answer[:500], claim_type=ClaimType.FACT, requires_external_evidence=True)]

        claims: list[Claim] = []
        for raw_claim in data.get("claims", []):
            try:
                ct = ClaimType(raw_claim.get("claim_type", "FACT"))
            except ValueError:
                ct = ClaimType.FACT

            numeric = raw_claim.get("numeric", False)
            ts = raw_claim.get("temporal_sensitive", False)
            hrd = raw_claim.get("high_risk_domain", False)
            vs = raw_claim.get("version_sensitive", False)

            claim = Claim(
                text=raw_claim["text"],
                claim_type=ct,
                risk_level=_assess_risk(ct, numeric, hrd, ts),
                requires_external_evidence=ct not in _NO_EVIDENCE_TYPES,
                temporal_sensitive=ts,
                version_sensitive=vs,
                numeric=numeric,
                high_risk_domain=hrd,
            )
            claims.append(claim)

        logger.info("Extracted %d claims", len(claims))
        return claims

    @staticmethod
    def _parse_json(text: str) -> dict:
        # Strip markdown fences if model adds them
        text = re.sub(r"^```(?:json)?\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)


claim_extractor = ClaimExtractor()
