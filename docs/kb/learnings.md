# Scan learnings

## 2026-11-05 - Initial project scan
- Trigger: User approved a full project analysis because the knowledge base did not exist.
- What worked: Scoped file enumeration to `app/`, `tests/`, and root configuration; source review plus targeted symbol searches exposed graph wiring, status, schema, and configuration mismatches. Running pytest from the service root verified the project suite.
- What went wrong / was missing: The first pytest invocation used the assistant's current repository instead of the selected service and failed during collection due to a cross-project path. Self-review also found the production app adds a second API prefix that router-only tests do not exercise. Both issues were checked against the selected service; its suite passed.
- Lesson (actionable rule for next time): For sibling projects, set the shell working directory explicitly before running project commands; establish test results only from the selected repository. Trace router prefixes through the production app mount and compare test mounting to it.
- KB files changed: index.md, overview.md, architecture.md, design-patterns.md, infrastructure.md, database.md, components/workflow-pipeline.md, components/api-persistence.md, components/mcp.md, components/email.md.
- Confidence: high

## 2026-11-09 - Worktree-aware incremental refresh
- Trigger: Refresh the KB for uncommitted API, PostgreSQL MCP, workflow, scheduler, and test changes.
- What worked: Compared Git status with the supplied list, then traced changed call paths and production router mounting. The service's own virtual environment suite passed 260 tests with one optional protocol test skipped.
- What went wrong / was missing: The prior KB described deleted direct database access, an unauthenticated API, old dependency metadata, and old workflow result handling. It also understated the output-guard typo: subject validation reads the missing attribute regardless of subject length. The system interpreter's test collection failed due to incompatible MCP/FastMCP imports; the project virtual environment passed. Git HEAD alone did not reveal worktree staleness. Additional MCP configuration changes were not in the supplied list.
- Lesson (actionable rule for next time): Check tracked and untracked worktree changes as well as HEAD, refresh affected source-backed entries, and use the selected project's virtual environment when testing. Record external integrations and optional protocol tests as gaps unless verified.
- KB files changed: index.md, overview.md, architecture.md, design-patterns.md, infrastructure.md, database.md, components/api-persistence.md, components/mcp.md, components/workflow-pipeline.md, components/email.md, learnings.md.
- Confidence: high

## 2026-11-10 - Provisional delivery and read-retry refresh
- Trigger: Refresh the supplied changed application, documentation and test areas, including uncommitted and untracked files.
- What worked: Compared worktree status to the supplied scope, traced new symbols into execution paths, read retry allowlist and delivery gate, and ran scoped tests with the project interpreter: 174 passed, one optional protocol test skipped.
- What went wrong / was missing: The prior KB omitted the provisional welcome renderer, email MCP client, delivery limiter and dormant verified-read retry policy. A HEAD-only freshness check would miss these uncommitted changes.
- Lesson (actionable rule for next time): Enumerate untracked files as well as tracked diffs, trace whether new components are actually wired, and distinguish implemented retry machinery from an enabled allowlist and fake acceptance from real delivery.
- KB files changed: index.md, architecture.md, design-patterns.md, infrastructure.md, database.md, components/email.md, components/mcp.md, learnings.md.
- Confidence: high

Sources: .python-version, pyproject.toml, requirements.txt, README.md, main.py, app/, tests/
Verified: 2026-11-10
