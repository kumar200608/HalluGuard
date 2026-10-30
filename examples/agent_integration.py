"""
Example: HalluGuard Integration with an AI Agent.

This shows the exact pattern for integrating the verification plugin into
any agent that generates text answers. The integration is a single function
call — verify_answer() — inserted between generation and delivery.

Architecture:
    User query
        ↓
    Agent generates draft answer
        ↓
    hallu_guard.verify_answer()   ← plugin intercepts here
        ↓
    Gate decision
        ↓
    Verified (possibly repaired) answer returned to user
"""
from __future__ import annotations

import asyncio
import os

# The plugin can be used locally or over HTTP
# This example shows the local in-process integration (same process as agent)

# ─────────────────────────────────────────────────────────────────────────────
# Option A: In-process integration (recommended for tightly-coupled agents)
# ─────────────────────────────────────────────────────────────────────────────

async def agent_with_guard_local(user_query: str) -> str:
    """
    Minimal agent loop with HalluGuard embedded.
    Replace `generate_draft()` with your actual LLM call.
    """
    # Step 1: Generate a draft answer (this is where hallucinations originate)
    draft = await generate_draft(user_query)

    # Step 2: Run the verification pipeline
    # Import is inside the function so this file can be read standalone
    from app.services.verification_pipeline import verify_answer

    response = await verify_answer(
        query=user_query,
        answer=draft,
        mode="standard",   # fast | standard | strict | critical
        debug=False,
    )

    print(f"Gate decision : {response.verification_report.gate_decision.value}")
    print(f"Risk level    : {response.verification_report.hallucination_risk.value}")
    print(f"Claims        : {len(response.verification_report.claims)}")
    print(f"Allowed       : {response.allowed}")

    if not response.allowed:
        print("\n⚠️  Original answer was modified or blocked.")
        for claim in response.verification_report.claims:
            if claim.status.value not in ("VERIFIED", "USER_PROVIDED"):
                print(f"  [{claim.status.value}] {claim.claim.text[:80]}")
                if claim.repair_instruction:
                    print(f"    → {claim.repair_instruction[:100]}")

    return response.answer


# ─────────────────────────────────────────────────────────────────────────────
# Option B: HTTP client integration (for agents in separate processes)
# ─────────────────────────────────────────────────────────────────────────────

async def agent_with_guard_http(user_query: str, api_base: str = "http://localhost:8000") -> str:
    """
    Agent integration via the REST API.
    Useful when HalluGuard runs as a microservice.
    """
    import httpx

    draft = await generate_draft(user_query)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{api_base}/v1/verify",
            json={
                "query": user_query,
                "answer": draft,
                "mode": "standard",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    print(f"Gate: {data['verification_report']['gate_decision']}")
    return data["answer"]


# ─────────────────────────────────────────────────────────────────────────────
# Simulated draft generator (replace with real LLM call)
# ─────────────────────────────────────────────────────────────────────────────

async def generate_draft(query: str) -> str:
    """
    Simulate an LLM that sometimes hallucinates.
    Replace this with your actual LLM provider call.
    """
    # Simulated hallucination scenarios
    hallucinations = {
        "iphone 99": "The iPhone 99 was released in January 2031 and features a 200MP camera with 16K video.",
        "python 4": "Python 4 was released in 2026. See https://python.org/python4",
        "20% of 500": "20% of 500 is 150.",
        "ceo of openai": "John Fabricator is the CEO of OpenAI.",
        "magic agent api": "Call POST /v2/magic-agent with your task payload.",
    }
    query_lower = query.lower()
    for key, hallu in hallucinations.items():
        if key in query_lower:
            return hallu

    # Safe fallback
    return f"I don't have specific information about: {query}"


# ─────────────────────────────────────────────────────────────────────────────
# Demo runner
# ─────────────────────────────────────────────────────────────────────────────

TEST_QUERIES = [
    "Tell me about the iPhone 99 specs.",
    "What is 20% of 500?",
    "Who is the CEO of OpenAI?",
    "How do I use Python 4?",
    "How do I call the /v2/magic-agent API?",
]


async def main():
    print("=" * 60)
    print("HalluGuard Agent Integration Demo")
    print("=" * 60)
    for query in TEST_QUERIES:
        print(f"\n{'─'*60}")
        print(f"QUERY: {query}")
        try:
            answer = await agent_with_guard_local(query)
            print(f"FINAL ANSWER: {answer[:300]}")
        except Exception as e:
            print(f"ERROR (expected without LLM configured): {e}")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
