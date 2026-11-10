# Project overview

Smoothie Email Subscription Service is a Python/FastAPI application intended to generate personalized subscriber welcome emails using LangGraph, serve administrative workflow history and trigger requests, and schedule new-registration processing. Its workflow and subscriber data now pass through a separate authenticated PostgreSQL MCP service rather than direct database connections.

The intended workflow is claim registration, fetch customer data, generate/review an email, deliver it, and record completion; the scheduler is designed to process bounded batches every ten minutes. **Email delivery is intentionally disabled**: `delivery_readiness.is_delivery_ready()` returns false, trigger requests return 503 before claims, and the scheduler does not start. All workflow routes require a configured operator bearer token and are mounted under `/api/api/workflows`.

Remaining source-level concerns include the missing graph input-validation state, guardrail configuration mismatches, and the uninitialized legacy email MCP registry. The Jev fallback and prompt examples have previously identified review risks; see [workflow pipeline](components/workflow-pipeline.md). Real database, delivery, and end-to-end operation are not established by unit tests.

Sources: README.md, main.py, app/api/auth.py, app/api/workflows.py, app/core/scheduler.py, app/services/delivery_readiness.py, app/services/postgres_workflows.py, app/services/workflow_execution.py, app/graph/executor.py, app/graph/workflow.py, app/agents/generator/node.py, app/guardrails/output_guards.py
Verified: 2026-11-09
