# HalluGuard — Hallucination Prevention & Verification Plugin

A production-grade, evidence-enforcement layer that sits between an AI agent and its final answer. Every factual claim must be traceable: **CLAIM → EVIDENCE → SOURCE → VERIFICATION → DECISION**.

---

## Architecture

```
User Request
    ↓
Intent Analyzer
    ↓
Agent Draft Generation
    ↓
┌─────────────────────────────────────────────┐
│           HALLUGUARD PLUGIN                 │
│                                             │
│  Claim Extractor                            │
│       ↓                                     │
│  Claim Classifier (24 types)                │
│       ↓                                     │
│  Evidence Retriever (Tier 1–4 sources)      │
│       ↓                                     │
│  Source Validator + Citation Checker        │
│       ↓                                     │
│  Entailment Checker (SUPPORTS/CONTRADICTS)  │
│       ↓                                     │
│  Contradiction Detector                     │
│       ↓                                     │
│  Temporal Validator                         │
│       ↓                                     │
│  Calculation Validator (deterministic)      │
│       ↓                                     │
│  Confidence Engine (0–1 score)              │
│       ↓                                     │
│  Hallucination Risk Engine (LOW→CRITICAL)   │
│       ↓                                     │
│  Answer Repairer (surgical edit)            │
│       ↓                                     │
│  Final Answer Gate (ALLOW/REWRITE/BLOCK)    │
└─────────────────────────────────────────────┘
    ↓
Verified Response
```

---

## Quick Start

### 1. Install dependencies

```bash
cd hallu_guard
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY, SEARCH_API_KEY, DATABASE_URL
```

### 3. Run with Docker

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`.

### 4. Run without Docker (development)

```bash
cd hallu_guard
PYTHONPATH=. uvicorn app.main:app --reload
```

---

## Plugin Integration

### In-process (recommended)

```python
from app.services.verification_pipeline import verify_answer

async def my_agent(user_query: str) -> str:
    draft = await your_llm_call(user_query)
    
    response = await verify_answer(
        query=user_query,
        answer=draft,
        mode="standard",   # fast | standard | strict | critical
    )
    
    return response.answer  # always use the verified answer
```

### Via HTTP API

```bash
curl -X POST http://localhost:8000/v1/verify \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is 20% of 500?",
    "answer": "20% of 500 is 150.",
    "mode": "standard"
  }'
```

Response:
```json
{
  "allowed": false,
  "answer": "20% of 500 is 100, not 150.",
  "verification_report": {
    "gate_decision": "BLOCK_AND_REGENERATE",
    "hallucination_risk": "HIGH",
    "claims": [
      {
        "text": "20% of 500 is 150.",
        "status": "CONTRADICTED",
        "calculation_verified": false,
        "repair_instruction": "Calculation error: stated 150.0, actual 100.0"
      }
    ]
  }
}
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/v1/verify` | POST | Full verification pipeline |
| `/v1/claims/extract` | POST | Extract claims from text |
| `/v1/sources/validate` | POST | Validate a URL |
| `/v1/metrics` | GET | Prometheus metrics |
| `/v1/metrics/summary` | GET | JSON metrics summary |
| `/docs` | GET | Interactive API docs |

---

## Verification Modes

| Mode | Description |
|---|---|
| `fast` | Only verify high-risk claims |
| `standard` | Verify all externally verifiable claims |
| `strict` | Verify every factual claim |
| `critical` | Require multiple authoritative sources |

---

## Claim Status Types

| Status | Meaning |
|---|---|
| `VERIFIED` | Supported by authoritative evidence |
| `PARTIALLY_VERIFIED` | Supported by partial evidence |
| `CONTRADICTED` | Evidence directly contradicts the claim |
| `UNSUPPORTED` | No evidence found |
| `UNVERIFIABLE` | Cannot be verified (no search access, etc.) |
| `INFERENCE` | The claim is a logical inference, not a fact |
| `OPINION` | The claim is subjective |
| `USER_PROVIDED` | Stated by the user, not externally verified |
| `VERIFICATION_UNAVAILABLE` | Service failure — system-level error |

---

## Gate Decisions

| Decision | Meaning |
|---|---|
| `ALLOW` | All important claims verified — return as-is |
| `REWRITE` | Minor issues — repair and return |
| `BLOCK_AND_REGENERATE` | High-risk unsupported claims — repair or reject |
| `REGENERATE_WITH_CONFLICT_DISCLOSURE` | Conflicting sources — disclose disagreement |
| `RETURN_UNCERTAIN_ANSWER` | Verification unavailable — return hedged answer |

---

## Source Tier Hierarchy

| Tier | Description | Examples |
|---|---|---|
| 1 | Primary | Official docs, government sites, academic papers, official APIs |
| 2 | Secondary | Established journalism, research institutions |
| 3 | Community | GitHub, Stack Overflow, Reddit |
| 4 | Low confidence | Anonymous blogs, scraped content |

Tier 3 and 4 sources are never treated as equivalent to primary evidence.

---

## Security

- All externally-retrieved content is wrapped as `UNTRUSTED_EVIDENCE`
- Prompt injection patterns are actively detected (12+ patterns)
- Secrets are never logged (API keys, tokens, passwords are redacted)
- Retrieved content cannot modify system instructions

---

## Configuration

All settings are via environment variables (see `.env.example`):

```bash
LLM_PROVIDER=openai          # LLM provider
LLM_MODEL=gpt-4o             # Model for generation
VERIFIER_MODEL=gpt-4o        # Separate model for verification
SEARCH_PROVIDER=tavily       # Web search provider
VERIFICATION_MODE=standard   # Default mode
CONFIDENCE_THRESHOLD=0.7     # Minimum confidence for VERIFIED status
SOURCE_FRESHNESS_LIMIT_DAYS=90  # Staleness threshold
ENABLE_WEB_VERIFICATION=true
ENABLE_CACHING=true
ENABLE_CODE_EXECUTION=false  # Sandbox code execution
MAX_RETRIES=3                # Max regeneration attempts
```

---

## Running Tests

```bash
cd hallu_guard

# Unit + benchmark tests (no LLM or network required)
PYTHONPATH=. python3 -m pytest tests/unit/ tests/benchmark/ -v

# All tests
PYTHONPATH=. python3 -m pytest -v

# With coverage
PYTHONPATH=. python3 -m pytest --cov=app tests/
```

---

## Project Structure

```
hallu_guard/
├── app/
│   ├── api/routes/          # FastAPI route handlers
│   ├── core/                # Config, enums, constants
│   ├── db/                  # SQLAlchemy ORM models
│   ├── models/              # Pydantic request/response schemas
│   ├── security/            # Prompt injection defense, sanitization
│   ├── services/            # Core verification components
│   │   ├── claim_extractor.py
│   │   ├── evidence_retriever.py
│   │   ├── entailment_checker.py
│   │   ├── contradiction_detector.py
│   │   ├── temporal_validator.py
│   │   ├── calculation_validator.py
│   │   ├── citation_validator.py
│   │   ├── confidence_engine.py
│   │   ├── answer_repairer.py
│   │   ├── answer_gate.py
│   │   └── verification_pipeline.py  ← main orchestrator
│   └── utils/               # Observability, logging
├── tests/
│   ├── unit/                # Deterministic unit tests
│   ├── integration/         # API integration tests (mocked)
│   └── benchmark/           # 10 hallucination scenarios
│       ├── golden_dataset.py
│       └── test_hallucination_scenarios.py
├── dashboard/               # Static monitoring dashboard
├── examples/                # Agent integration examples
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Design Principles

1. **Never allow LLM self-verification** — "Am I hallucinating? No." is NOT verification.
2. **External evidence only** — claims require traceable sources, not model confidence.
3. **Separate generator and verifier** — the verifier model never sees the generator's reasoning.
4. **Deterministic validators take precedence** — calculations go to a Python evaluator, never an LLM.
5. **Fail-safe default** — if verification fails, acknowledge uncertainty rather than pass unsupported claims.
6. **Surgical repair** — only unsupported portions are rewritten; verified claims are unchanged.
7. **Treat retrieved content as data** — external content can never override system instructions.
