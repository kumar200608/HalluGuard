"""Pydantic models for the entire verification pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.enums import (
    ClaimType,
    EntailmentResult,
    GateDecision,
    HallucinationRisk,
    SourceTier,
    VerificationMode,
    VerificationStatus,
)


# ---------------------------------------------------------------------------
# Source & Evidence
# ---------------------------------------------------------------------------

class SourceMetadata(BaseModel):
    url: str
    domain: str = ""
    title: str = ""
    author: str = ""
    organization: str = ""
    publication_date: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    tier: SourceTier = SourceTier.TIER3_COMMUNITY
    http_status: Optional[int] = None
    is_available: bool = True
    is_canonical: bool = True
    canonical_url: str = ""


class EvidenceChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str = ""
    source: SourceMetadata
    text: str
    page: Optional[int] = None
    section: str = ""
    entailment: EntailmentResult = EntailmentResult.INSUFFICIENT_CONTEXT
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

class Claim(BaseModel):
    id: str = Field(default_factory=lambda: f"C{str(uuid4())[:8].upper()}")
    text: str
    claim_type: ClaimType = ClaimType.FACT
    risk_level: HallucinationRisk = HallucinationRisk.MEDIUM
    requires_external_evidence: bool = True
    temporal_sensitive: bool = False
    version_sensitive: bool = False
    numeric: bool = False
    high_risk_domain: bool = False  # medical/legal/financial/political
    dependency_ids: list[str] = Field(default_factory=list)  # claim graph


class ClaimVerificationResult(BaseModel):
    claim: Claim
    status: VerificationStatus = VerificationStatus.UNSUPPORTED
    confidence: float = 0.0
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    contradictions: list[EvidenceChunk] = Field(default_factory=list)
    temporal_valid: Optional[bool] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    repair_instruction: str = ""
    calculation_verified: Optional[bool] = None
    fake_citation_detected: bool = False


# ---------------------------------------------------------------------------
# Verification request / response
# ---------------------------------------------------------------------------

class VerificationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    query: str
    answer: str
    context: Optional[str] = None
    mode: VerificationMode = VerificationMode.STANDARD
    debug: bool = False


class VerificationReport(BaseModel):
    request_id: str
    query: str
    original_answer: str
    verified_answer: str
    claims: list[ClaimVerificationResult] = Field(default_factory=list)
    overall_status: VerificationStatus = VerificationStatus.UNSUPPORTED
    gate_decision: GateDecision = GateDecision.BLOCK_AND_REGENERATE
    hallucination_risk: HallucinationRisk = HallucinationRisk.HIGH
    risk_score: float = 0.0
    citations: list[SourceMetadata] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    regeneration_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    debug_info: Optional[dict[str, Any]] = None


class VerificationResponse(BaseModel):
    allowed: bool
    answer: str
    verification_report: VerificationReport


# ---------------------------------------------------------------------------
# API sub-endpoint models
# ---------------------------------------------------------------------------

class ExtractClaimsRequest(BaseModel):
    text: str
    context: Optional[str] = None


class ExtractClaimsResponse(BaseModel):
    claims: list[Claim]


class ValidateSourceRequest(BaseModel):
    url: str
    claim_text: str


class ValidateSourceResponse(BaseModel):
    source: SourceMetadata
    entailment: EntailmentResult
    summary: str


class RepairAnswerRequest(BaseModel):
    original_answer: str
    claims: list[ClaimVerificationResult]


class RepairAnswerResponse(BaseModel):
    repaired_answer: str
    changes: list[str]
