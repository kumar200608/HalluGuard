"""Claim-level sub-endpoints.

POST /v1/claims/extract   — extract claims from text
POST /v1/claims/verify    — verify a specific claim (no full pipeline)
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import ExtractClaimsRequest, ExtractClaimsResponse
from app.services.claim_extractor import claim_extractor

router = APIRouter()


@router.post("/claims/extract", response_model=ExtractClaimsResponse)
async def extract_claims(request: ExtractClaimsRequest) -> ExtractClaimsResponse:
    """Extract and classify all atomic claims from a text passage."""
    claims = await claim_extractor.extract(
        query="",
        answer=request.text,
        context=request.context or "",
    )
    return ExtractClaimsResponse(claims=claims)
