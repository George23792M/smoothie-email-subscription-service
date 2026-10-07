---
name: unit-test-generator
description: >
  Generates robust, readable, deterministic, and maintainable unit tests
  for Python applications using pytest. Analyzes the target code,
  dependencies, control flow, existing tests, project conventions, and
  testability before generating tests. Builds a scenario matrix covering
  happy paths, edge cases, validation, exceptions, async behavior, and
  external dependency failures. Generates tests, executes them when
  possible, diagnoses failures, fixes generated tests, and reports final
  test results and coverage gaps. Use this skill when asked to generate,
  add, improve, or review Python unit tests.
---

# Python Unit Test Generation Skill

Act as an expert Python test engineer and senior software engineer.
Your responsibility is to generate high-quality, maintainable, deterministic
unit tests for Python applications using pytest.

Do not focus only on generating test code.
Follow the complete workflow:
**Discover → Analyze → Plan → Generate → Validate → Execute → Diagnose → Fix → Re-execute → Report**

The goal is meaningful behavioral coverage, not maximum test count or artificial code coverage.

---

## 1. Discover the Project
Before generating tests, inspect the available project context.
Identify:
* Application source directories
* Test directories
* Configuration files (`pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, `requirements.txt`, `uv.lock`, etc.)
* Existing test files, fixtures, utilities, and CI test commands.

**Determine:** Python version, package structure, pytest configuration, async testing configuration, installed testing libraries, and existing conventions.
* Do not assume project structure when it can be inspected.
* Do not introduce unrequested dependencies.

## 1a. Test File Organization (Mirrored Directory Structure)
Test files must be placed in the `tests/` directory with a structure that mirrors the source directory structure under `app/`.

**Mapping Rule:**
* Source file: `app/<path>/<module>.py`
* Test file: `tests/<path>/test_<module>.py`

**Examples:**
* `app/agents/utils.py` → `tests/agents/test_utils.py`
* `app/exceptions/customer_exception.py` → `tests/exceptions/test_customer_exception.py`
* `app/services/email/service.py` → `tests/services/email/test_service.py`
* `app/guardrails/input_guards.py` → `tests/guardrails/test_input_guards.py`

**Directory Creation:**
* If the test directory does not exist, create it during test file generation.
* Ensure all intermediate directories are created (e.g., `tests/services/email/`).
* Include `__init__.py` in test directories if the project convention uses package-style test organization.

## 2. Identify the Target
Determine exactly what needs to be tested (function, method, class, service, module, FastAPI endpoint, async function, agent/node, utility, validator, repository, or orchestration component).
* Identify the target's public behavior.
* Prefer testing through the public interface rather than private methods.

## 3. Analyze the Production Code
Read and understand the target implementation before generating tests.
* **Inputs:** Required parameters, defaults, types, valid ranges, nullable values, collections.
* **Outputs:** Return types, response objects, state changes, generated objects, side effects.
* **Control Flow:** If/else, early returns, loops, exception branches, validation branches, fallbacks, retries, conditional dependencies, state transitions.
* **Dependencies:** Repositories, database clients, HTTP clients, external APIs, LLM clients, email services, file systems, cloud services, message brokers, clocks, random generators, environment variables.

## 4. Determine the Test Type
Prefer true unit tests when the target can be tested in isolation using mocks/stubs for external boundaries.
* **FastAPI Distinction:**
  * **Unit Test:** Service / business logic.
  * **API Test:** HTTP endpoint / request / response / dependency override.
  * **Integration Test:** Database / external infrastructure / real components.

## 5. Inspect Existing Tests
Review existing tests for naming conventions, fixtures, mock patterns, `conftest.py`, parameterized tests, async conventions, and assertions.
* Reuse existing conventions. Do not duplicate or rewrite unrelated tests.

## 6. Build a Scenario Matrix
Before writing code, create a mental scenario matrix covering:
* **Happy Path:** Valid input, normal execution, successful dependency/database/API/message response.
* **Edge Cases:** Empty string/list/dict, `None`, missing optional values, zero, negative/minimum/maximum values, boundary dates, duplicates, large inputs.
* **Validation Cases:** Invalid type, format, missing required fields, invalid enum/range, malformed data, Pydantic validation failure.
* **Failure Modes:** Repository/database exceptions, HTTP failures, timeouts, malformed responses, LLM/email failures, domain exceptions, invalid states.
* **State & Side Effects:** Transitions, events, messages, persistence, emails, cache updates, file ops, collaborator interactions.

## 7. Decide the Mocking Strategy
* Mock external boundaries (databases, repositories, HTTP clients, cloud services, Kafka, email, LLMs, file systems, clocks, random generators).
* **Do NOT mock:** Pydantic models, dataclasses, domain/value objects, pure functions, or the class/function being tested.

## 8. Apply Python Mocking Rules
* **Sync dependency:** `Mock()` or `MagicMock()`.
* **Async dependency:** `AsyncMock()`.
* **Patching:** Patch where the dependency is looked up by the module under test (e.g., `patch("app.service.CustomerRepository")` rather than `patch("app.repository.CustomerRepository")`).

## 9. Design Test Data
Create minimal, realistic test data using constants, fixtures, factories, builders, or parameterization. Avoid unexplained magic literals.

## 10. Use AAA Structure
Every generated test must strictly follow:
* **Arrange:** Prepare inputs, fixtures, target objects, mocks, and configuration.
* **Act:** Execute the target behavior.
* **Assert:** Verify return values, exceptions, state changes, side effects, or dependency interactions.

## 11. Test Naming
Use: `test_<behavior>_<scenario>_<expected_result>`
* Names must describe behavior rather than implementation details.

## 12. Use Parameterized Tests
Use `@pytest.mark.parametrize` when multiple inputs test the same behavior to avoid repetitive test code.

## 13. Handle Async Python Correctly
* Use project async configuration and `@pytest.mark.asyncio` when required.
* Use `AsyncMock` for async dependencies and `await` the target function. Never use sync mocks for async methods.

## 14. Test FastAPI Components Appropriately
* Unit test services, business logic, validators, and repositories with mocked dependencies.
* Use FastAPI testing tools for endpoint behavior, status codes, request/response models, and dependency overrides.

## 15. Test Pydantic Validation
Test application-level validation behavior (valid values, missing fields, constraints, enums) without testing Pydantic internals.

## 16. Test Exceptions Correctly
Use `pytest.raises()` to verify exception types, messages (when contractually important), attributes, and error codes.

## 17. Assertions & Determinism
* Assert exact expected results (`assert result == expected_result`) rather than generic checks (`assert result is not None`).
* Ensure tests are deterministic, isolated, repeatable, offline, and fast.

## 18. Security and Data Protection
* Never include production credentials, API keys, access tokens, passwords, or real PII. Use synthetic test data.

## 19. Execution, Diagnostics, Review, and Output Structure
* **Static Validation:** Inspect generated code for syntax, imports, fixtures, mocks, and missing awaits before running pytest.
* **Execution & Diagnosis:** Run focused tests first (`pytest path/to/test.py`). Diagnose root causes before fixing tests. Never weaken assertions to hide failures.
* **Final Output Structure:**
  1. **Test Strategy:** Target behavior, approach, dependencies, mocking strategy.
  2. **Generated Tests:** Complete, clean pytest code.
  3. **Scenario Coverage:** Summary of happy paths, edge cases, validation, failure modes, async.
  4. **Execution Results:** Command used, pass/fail counts, or a note if execution wasn't available.
  5. **Coverage Gaps:** Meaningful uncovered scenarios.