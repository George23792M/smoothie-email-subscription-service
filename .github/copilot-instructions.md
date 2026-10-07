# GitHub Copilot Instructions - Python & LangGraph Agent Development

## 1. Stack & Types
- Python 3.12+, strict PEP 8, structural pattern matching, `pathlib`.
- Mandatory strict type hints (e.g., `str | None`, `list[str]`; avoid `Any`).
- Google-style docstrings (Args, Returns, Raises) on all public APIs.

## 2. Architecture & Patterns
- Enforce SOLID, DRY, and high cohesion. Functions under 30 lines.
- No magic numbers or obscure abbreviations. Extract complex conditionals to helpers.
- Validations & schemas: Use Pydantic v2 `BaseModel` and field constraints.
- Flow: Use explicit pipelines, registries, or factory patterns.
- Resilience: Wrap all LLM calls/side-effects in specific `try/except` blocks.
- Telemetry: Track transitions, pipelines, and errors via standard `logging`.

## 3. Mandatory Output Format
Return code followed ONLY by these two headers (no other chat/intros):
### How it works: [Concise step-by-step logic]
### Professional Best Practice: [Short educational reasoning]
