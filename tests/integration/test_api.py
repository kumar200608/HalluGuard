"""Integration test for the FastAPI routes (no LLM, no network — mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.main import app
from app.core.enums import GateDecision, HallucinationRisk, VerificationStatus
from app.models.schemas import (
    VerificationReport,
    VerificationResponse,
)


@pytest.fixture
def mock_pipeline_response():
    from app.models.schemas import VerificationReport, VerificationResponse
    from app.core.enums import GateDecision, HallucinationRisk, VerificationStatus

    report = VerificationReport(
        request_id="test-123",
        query="What is the capital of France?",
        original_answer="The capital of France is Paris.",
        verified_answer="The capital of France is Paris.",
        overall_status=VerificationStatus.VERIFIED,
        gate_decision=GateDecision.ALLOW,
        hallucination_risk=HallucinationRisk.LOW,
        risk_score=5.0,
    )
    return VerificationResponse(
        allowed=True,
        answer="The capital of France is Paris.",
        verification_report=report,
    )


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_verify_endpoint_structure(mock_pipeline_response):
    with patch("app.api.routes.verify.pipeline.run", AsyncMock(return_value=mock_pipeline_response)):
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.post(
                "/v1/verify",
                json={
                    "query": "What is the capital of France?",
                    "answer": "The capital of France is Paris.",
                    "mode": "standard",
                },
            )
    assert resp.status_code == 200
    data = resp.json()
    assert "allowed" in data
    assert "answer" in data
    assert "verification_report" in data
    assert data["allowed"] is True


@pytest.mark.asyncio
async def test_extract_claims_endpoint():
    mock_claims = []
    with patch(
        "app.api.routes.claims.claim_extractor.extract",
        AsyncMock(return_value=mock_claims),
    ):
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.post(
                "/v1/claims/extract",
                json={"text": "OpenAI released GPT-4 in March 2023."},
            )
    assert resp.status_code == 200
    assert "claims" in resp.json()
