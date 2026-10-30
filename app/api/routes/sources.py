"""Source validation endpoint.

POST /v1/sources/validate — check if a URL is reachable and supports a claim
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import ValidateSourceRequest, ValidateSourceResponse
from app.services.citation_validator import citation_validator
from app.services.evidence_retriever import _classify_domain
from app.models.schemas import SourceMetadata
from app.core.enums import EntailmentResult

router = APIRouter()


@router.post("/sources/validate", response_model=ValidateSourceResponse)
async def validate_source(request: ValidateSourceRequest) -> ValidateSourceResponse:
    """Check if a URL is reachable and return its tier/availability."""
    source_meta, warning = await citation_validator._validate_single(request.url)
    if source_meta is None:
        from urllib.parse import urlparse
        domain = urlparse(request.url).netloc.lstrip("www.")
        source_meta = SourceMetadata(url=request.url, domain=domain, is_available=False)

    entailment = EntailmentResult.INSUFFICIENT_CONTEXT
    summary = warning or "URL is reachable. Entailment not checked without passage text."

    return ValidateSourceResponse(
        source=source_meta,
        entailment=entailment,
        summary=summary,
    )
