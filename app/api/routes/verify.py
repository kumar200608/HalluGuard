"""Main verification endpoints.

POST /v1/verify          — full pipeline
GET  /v1/verification/{id} — retrieve stored report
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.models.schemas import VerificationRequest, VerificationResponse
from app.services.verification_pipeline import pipeline
from app.utils.observability import audit_log

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/verify", response_model=VerificationResponse)
async def verify(
    request: VerificationRequest,
    background_tasks: BackgroundTasks,
) -> VerificationResponse:
    """
    Full hallucination verification pipeline.

    - Extracts claims from the agent answer
    - Retrieves evidence for each claim
    - Checks entailment, contradictions, temporality, calculations
    - Decides ALLOW / REWRITE / BLOCK_AND_REGENERATE
    - Returns the verified (possibly repaired) answer
    """
    try:
        response = await pipeline.run(request)
    except Exception as exc:
        logger.error("Pipeline error [%s]: %s", request.request_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Verification pipeline failed: {exc}")

    # Async audit logging
    background_tasks.add_task(
        audit_log,
        request_id=request.request_id,
        event="verification_complete",
        detail={
            "gate": response.verification_report.gate_decision.value,
            "risk": response.verification_report.hallucination_risk.value,
            "claims": len(response.verification_report.claims),
        },
    )
    return response
