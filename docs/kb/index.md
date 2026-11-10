Last scan: 2026-11-10
Commit: 6a4b8138b05c1247bcc336a90e0716e76f9aee2a

# Knowledge Base

## Contents
- [Overview](overview.md)
- [Architecture](architecture.md)
- [Design patterns](design-patterns.md)
- [Infrastructure and configuration](infrastructure.md)
- [Database](database.md)
- [Workflow and agents](components/workflow-pipeline.md)
- [API and persistence](components/api-persistence.md)
- [MCP integration](components/mcp.md)
- [Email integrations](components/email.md)
- [Scan learnings](learnings.md)

## Scanned areas
- Incremental refresh of uncommitted API, settings, scheduler, DAOs, workflow execution, PostgreSQL and email MCP clients, provisional welcome renderer and delivery limits, dependency metadata, README and relevant tests.
- Previous full scan covered generator, critic, refiner, prompts, legacy MCP, email, exceptions and logging. Unchanged areas retain prior findings rather than being fully rescanned.
- HEAD is recorded above, but this scan includes uncommitted and untracked worktree files; the hash alone does not identify this snapshot.
- Scoped project virtual environment test run on 2026-11-10: 174 passed, 1 optional protocol test skipped, 10 warnings. The 2026-11-09 full-suite result was 260 passed, 1 skipped.

## Known gaps
- Email delivery is deliberately disabled; real delivery, full production workflow, and automatic recovery are unverified. Graph input and guardrail defects remain.
- External PostgreSQL MCP server implementation, schema/migrations, deployment, actual database connectivity and network exposure were not scanned or verified.
- The optional cross-repository protocol test was deliberately skipped in this run by clearing its server checkout/interpreter settings; it uses a fake database even when enabled.
- The new welcome template, email MCP contract and provider acceptance semantics are provisional and not integrated into workflow execution. The limiter is process-local and not wired into that execution path. The PostgreSQL verified-read allowlist is empty, so its retry implementation is inactive.
- Router paths retain the double `/api` prefix; the operator token does not identify individual customers and throttling is process-local, not shared across replicas.
- Git status also showed changed `.vscode/mcp.json` and untracked `.mcp.json`, outside the supplied changed-file list. Their contents were not reviewed in this refresh; their effects remain a gap. Docs other than README and the KB were not scanned.

Sources: README.md, pyproject.toml, requirements.txt, main.py, app/, tests/, .vscode/mcp.json, .mcp.json, .github/
Verified: 2026-11-10
