"""
Unit tests for app/agents/utils.py

Test Coverage:
- Correlation ID generation (uniqueness, format)
- JSON extraction from text (markdown, direct, edge cases)
- LLM response parsing and validation
- Context builders (generation, critic)
- Logging functions (basic invocation)

All tests are deterministic, offline, and use mocked dependencies.
"""

import json
import logging
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from app.agents.utils import (
    build_critic_context,
    build_generation_context,
    extract_json_from_text,
    generate_correlation_id,
    log_metric,
    log_node_entry,
    log_node_exit,
    parse_llm_response,
)
from app.graph.state import EmailContent
from app.schemas.responses import CustomerDetailResponse

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_customer_data() -> CustomerDetailResponse:
    """Valid customer with all fields populated."""
    return CustomerDetailResponse(
        customer_id="cust_12345",
        first_name="Sarah",
        last_name="Smith",
        customer_name="Sarah Smith",
        preferred_name="Sarah",
        email="sarah@example.com",
        plan_name="Premium",
    )


@pytest.fixture
def sample_customer_minimal() -> CustomerDetailResponse:
    """Minimal customer (no preferred_name)."""
    return CustomerDetailResponse(
        customer_id="cust_minimal",
        first_name="John",
        last_name="Doe",
        customer_name="John Doe",
        preferred_name=None,
        email="john@example.com",
        plan_name=None,
    )


@pytest.fixture
def valid_email_json() -> dict[str, Any]:
    """Valid EmailContent JSON structure."""
    return {
        "subject": "Welcome to Premium!",
        "body": "We're excited to have you on board.",
        "personalized_elements": ["first_name", "plan_name"],
    }


@pytest.fixture
def valid_llm_response_direct_json(valid_email_json: dict[str, Any]) -> str:
    """LLM response with direct JSON."""
    return json.dumps(valid_email_json)


@pytest.fixture
def valid_llm_response_markdown_json(valid_email_json: dict[str, Any]) -> str:
    """LLM response with markdown JSON code block."""
    return f"```json\n{json.dumps(valid_email_json)}\n```"


@pytest.fixture
def valid_llm_response_generic_markdown(valid_email_json: dict[str, Any]) -> str:
    """LLM response with generic markdown code block."""
    return f"Here's the email:\n```\n{json.dumps(valid_email_json)}\n```"


# ============================================================================
# TEST: generate_correlation_id()
# ============================================================================


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id() function."""

    def test_returns_hex_string(self) -> None:
        """Happy path: Returns valid hex string."""
        # Act
        correlation_id = generate_correlation_id()

        # Assert
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 32  # UUID4 hex is 32 chars
        assert all(c in "0123456789abcdef" for c in correlation_id)

    def test_uniqueness(self) -> None:
        """Edge case: Multiple calls generate unique IDs."""
        # Act
        ids = [generate_correlation_id() for _ in range(100)]

        # Assert
        assert len(set(ids)) == 100  # All unique

    def test_deterministic_with_mocked_uuid(self) -> None:
        """Mocking: Returns predictable value when uuid.uuid4() is mocked."""
        # Arrange
        with patch("app.agents.utils.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"

            # Act
            correlation_id = generate_correlation_id()

            # Assert
            assert correlation_id == "abc123def456"


# ============================================================================
# TEST: extract_json_from_text()
# ============================================================================


class TestExtractJsonFromText:
    """Tests for extract_json_from_text() function."""

    def test_direct_json_parsing(self, valid_email_json: dict[str, Any]) -> None:
        """Happy path: Extract direct JSON."""
        # Arrange
        text = json.dumps(valid_email_json)

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result == valid_email_json
        assert result["subject"] == "Welcome to Premium!"

    def test_markdown_json_block(self, valid_email_json: dict[str, Any]) -> None:
        """Happy path: Extract JSON from markdown code block (```json)."""
        # Arrange
        text = f"```json\n{json.dumps(valid_email_json)}\n```"

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result == valid_email_json

    def test_generic_markdown_block(self, valid_email_json: dict[str, Any]) -> None:
        """Happy path: Extract JSON from generic markdown code block (```)."""
        # Arrange
        text = f"Here is the data:\n```\n{json.dumps(valid_email_json)}\n```"

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result == valid_email_json

    def test_markdown_with_surrounding_text(
        self, valid_email_json: dict[str, Any]
    ) -> None:
        """Edge case: JSON block surrounded by explanatory text."""
        # Arrange
        text = (
            "Here's your generated email:\n"
            f"```json\n{json.dumps(valid_email_json)}\n```\n"
            "Please review and send."
        )

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result == valid_email_json

    def test_empty_string_raises_value_error(self) -> None:
        """Validation: Empty string raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="non-empty string"):
            extract_json_from_text("")

    def test_whitespace_only_raises_value_error(self) -> None:
        """Validation: Whitespace-only string raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="non-empty string"):
            extract_json_from_text("   \n\t  ")

    def test_none_input_raises_value_error(self) -> None:
        """Validation: None input raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="non-empty string"):
            extract_json_from_text(None)  # type: ignore

    def test_non_string_input_raises_value_error(self) -> None:
        """Validation: Non-string input raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="non-empty string"):
            extract_json_from_text(123)  # type: ignore

    def test_malformed_json_raises_value_error(self) -> None:
        """Failure mode: Invalid JSON syntax raises ValueError."""
        # Arrange
        text = '{"subject": "test", "body": "incomplete'

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid JSON"):
            extract_json_from_text(text)

    def test_json_without_code_block_markers(self) -> None:
        """Edge case: JSON in plain text without code block markers."""
        # Arrange
        text = '{"subject": "test", "body": "hello", "personalized_elements": []}'

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result["subject"] == "test"

    def test_nested_json_structure(self) -> None:
        """Edge case: Nested JSON objects are preserved."""
        # Arrange
        complex_data = {
            "subject": "Test",
            "body": "Body",
            "personalized_elements": ["name", "email"],
            "metadata": {"version": 1, "tags": ["urgent", "promo"]},
        }
        text = f"```json\n{json.dumps(complex_data)}\n```"

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert result["metadata"]["version"] == 1
        assert "urgent" in result["metadata"]["tags"]

    def test_multiple_code_blocks_uses_first(
        self, valid_email_json: dict[str, Any]
    ) -> None:
        """Edge case: Multiple code blocks - extract from first."""
        # Arrange
        other_json = {"ignore": "this"}
        text = (
            f"```json\n{json.dumps(valid_email_json)}\n```\n"
            f"```json\n{json.dumps(other_json)}\n```"
        )

        # Act
        result = extract_json_from_text(text)

        # Assert
        assert "subject" in result
        assert "ignore" not in result


# ============================================================================
# TEST: parse_llm_response()
# ============================================================================


class TestParseLlmResponse:
    """Tests for parse_llm_response() function."""

    def test_valid_direct_json(self, valid_llm_response_direct_json: str) -> None:
        """Happy path: Parse valid JSON response."""
        # Act
        result = parse_llm_response(valid_llm_response_direct_json)

        # Assert
        assert isinstance(result, EmailContent)
        assert result.subject == "Welcome to Premium!"
        assert result.body == "We're excited to have you on board."
        assert result.personalized_elements == ["first_name", "plan_name"]

    def test_valid_markdown_json(self, valid_llm_response_markdown_json: str) -> None:
        """Happy path: Parse JSON from markdown."""
        # Act
        result = parse_llm_response(valid_llm_response_markdown_json)

        # Assert
        assert isinstance(result, EmailContent)
        assert result.subject == "Welcome to Premium!"

    def test_valid_generic_markdown(
        self, valid_llm_response_generic_markdown: str
    ) -> None:
        """Happy path: Parse JSON from generic markdown."""
        # Act
        result = parse_llm_response(valid_llm_response_generic_markdown)

        # Assert
        assert isinstance(result, EmailContent)
        assert result.body == "We're excited to have you on board."

    def test_missing_required_field_raises_validation_error(self) -> None:
        """Validation: Missing required field raises ValueError."""
        # Arrange
        text = json.dumps(
            {
                "subject": "Test",
                # Missing "body" and "personalized_elements"
            }
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid email content"):
            parse_llm_response(text)

    def test_invalid_type_raises_validation_error(self) -> None:
        """Validation: Wrong type for field raises ValueError."""
        # Arrange
        text = json.dumps(
            {
                "subject": "Test",
                "body": "Body",
                "personalized_elements": "not_a_list",  # Should be list
            }
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid email content"):
            parse_llm_response(text)

    def test_extra_fields_accepted(self) -> None:
        """Edge case: Extra fields in JSON are ignored (Pydantic default)."""
        # Arrange
        text = json.dumps(
            {
                "subject": "Test",
                "body": "Body",
                "personalized_elements": ["name"],
                "extra_field": "ignored",  # Not in EmailContent
            }
        )

        # Act
        result = parse_llm_response(text)

        # Assert
        assert isinstance(result, EmailContent)
        assert result.subject == "Test"
        assert not hasattr(result, "extra_field")

    def test_malformed_json_raises_value_error(self) -> None:
        """Failure mode: Malformed JSON raises ValueError."""
        # Arrange
        text = '{"subject": "incomplete'

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_llm_response(text)

    def test_empty_string_raises_value_error(self) -> None:
        """Failure mode: Empty string raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError):
            parse_llm_response("")

    def test_personalized_elements_empty_list_valid(self) -> None:
        """Edge case: Empty personalized_elements list is valid."""
        # Arrange
        text = json.dumps(
            {
                "subject": "Test",
                "body": "Body",
                "personalized_elements": [],
            }
        )

        # Act
        result = parse_llm_response(text)

        # Assert
        assert result.personalized_elements == []

    def test_subject_and_body_empty_strings_valid(self) -> None:
        """Edge case: Empty subject/body strings are valid (Pydantic allows)."""
        # Arrange
        text = json.dumps(
            {
                "subject": "",
                "body": "",
                "personalized_elements": [],
            }
        )

        # Act
        result = parse_llm_response(text)

        # Assert
        assert result.subject == ""
        assert result.body == ""


# ============================================================================
# TEST: build_generation_context()
# ============================================================================


class TestBuildGenerationContext:
    """Tests for build_generation_context() function."""

    def test_all_fields_provided(
        self, sample_customer_data: CustomerDetailResponse
    ) -> None:
        """Happy path: All customer fields populated."""
        # Act
        context = build_generation_context(sample_customer_data)

        # Assert
        assert context["customer_id"] == "cust_12345"
        assert context["customer_name"] == "Sarah"  # preferred_name takes priority
        assert context["first_name"] == "Sarah"
        assert context["last_name"] == "Smith"
        assert context["plan_name"] == "Premium"
        assert context["email"] == "sarah@example.com"
        assert "timestamp" in context
        assert isinstance(context["timestamp"], str)

    def test_preferred_name_used_when_available(
        self, sample_customer_data: CustomerDetailResponse
    ) -> None:
        """Happy path: preferred_name prioritized over customer_name."""
        # Act
        context = build_generation_context(sample_customer_data)

        # Assert
        assert context["customer_name"] == "Sarah"  # preferred_name

    def test_customer_name_used_when_preferred_missing(
        self, sample_customer_minimal: CustomerDetailResponse
    ) -> None:
        """Edge case: customer_name used when preferred_name is None."""
        # Act
        context = build_generation_context(sample_customer_minimal)

        # Assert
        assert context["customer_name"] == "John Doe"

    def test_fallback_to_first_last_name(self) -> None:
        """Edge case: Construct name from first_name + last_name."""
        # Arrange
        customer = CustomerDetailResponse(
            customer_id="cust_fallback",
            first_name="Alice",
            last_name="Wonder",
            customer_name="",  # Empty string forces fallback
            preferred_name=None,
            email="alice@example.com",
        )

        # Act
        context = build_generation_context(customer)

        # Assert
        assert context["customer_name"] == "Alice Wonder"

    def test_plan_name_defaults_to_standard(
        self, sample_customer_minimal: CustomerDetailResponse
    ) -> None:
        """Edge case: plan_name defaults to 'Standard' when None."""
        # Act
        context = build_generation_context(sample_customer_minimal)

        # Assert
        assert context["plan_name"] == "Standard"

    def test_timestamp_is_iso_format(
        self, sample_customer_data: CustomerDetailResponse
    ) -> None:
        """Validation: Timestamp is ISO 8601 format."""
        # Arrange
        with patch("app.agents.utils.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = (
                "2024-01-15T10:30:00"
            )

            # Act
            context = build_generation_context(sample_customer_data)

            # Assert
            assert context["timestamp"] == "2024-01-15T10:30:00"

    def test_cannot_determine_customer_name_raises_error(self) -> None:
        """Failure mode: All name fields empty/None raises ValueError."""
        # Arrange
        customer = CustomerDetailResponse(
            customer_id="cust_noname",
            first_name="",
            last_name="",
            customer_name="",
            preferred_name=None,
            email="test@example.com",
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot determine customer name"):
            build_generation_context(customer)

    def test_context_is_dict_type(
        self, sample_customer_data: CustomerDetailResponse
    ) -> None:
        """Validation: Return value is a dict."""
        # Act
        context = build_generation_context(sample_customer_data)

        # Assert
        assert isinstance(context, dict)

    def test_context_has_required_keys(
        self, sample_customer_data: CustomerDetailResponse
    ) -> None:
        """Validation: Context has all required keys."""
        # Act
        context = build_generation_context(sample_customer_data)

        # Assert
        required_keys = {
            "customer_id",
            "customer_name",
            "first_name",
            "last_name",
            "plan_name",
            "email",
            "timestamp",
        }
        assert set(context.keys()) >= required_keys


# ============================================================================
# TEST: build_critic_context()
# ============================================================================


class TestBuildCriticContext:
    """Tests for build_critic_context() function."""

    def test_all_parameters_provided(self) -> None:
        """Happy path: All parameters populated."""
        # Arrange
        customer_name = "Sarah Smith"
        plan_name = "Premium"
        subject = "Welcome!"
        body = "We're excited to have you."

        # Act
        context = build_critic_context(customer_name, plan_name, subject, body)

        # Assert
        assert context["customer_name"] == "Sarah Smith"
        assert context["plan_name"] == "Premium"
        assert context["email_subject"] == "Welcome!"
        assert context["email_body_preview"] == "We're excited to have you."

    def test_plan_name_none_defaults_to_standard(self) -> None:
        """Edge case: plan_name=None defaults to 'Standard'."""
        # Arrange
        context = build_critic_context("John Doe", None, "Subject", "Body")

        # Assert
        assert context["plan_name"] == "Standard"

    def test_body_preview_truncated_to_500_chars(self) -> None:
        """Edge case: Long body is truncated to first 500 characters."""
        # Arrange
        long_body = "x" * 1000  # 1000 chars

        # Act
        context = build_critic_context("Name", "Plan", "Subject", long_body)

        # Assert
        assert len(context["email_body_preview"]) == 500
        assert context["email_body_preview"] == "x" * 500

    def test_short_body_not_truncated(self) -> None:
        """Edge case: Short body is kept as-is."""
        # Arrange
        short_body = "Short email body"

        # Act
        context = build_critic_context("Name", "Plan", "Subject", short_body)

        # Assert
        assert context["email_body_preview"] == short_body

    def test_empty_strings_accepted(self) -> None:
        """Edge case: Empty strings are valid (no validation)."""
        # Act
        context = build_critic_context("", "", "", "")

        # Assert
        assert context["customer_name"] == ""
        assert context["email_subject"] == ""

    def test_context_is_dict_type(self) -> None:
        """Validation: Return value is a dict."""
        # Act
        context = build_critic_context("Name", "Plan", "Subject", "Body")

        # Assert
        assert isinstance(context, dict)

    def test_context_has_required_keys(self) -> None:
        """Validation: Context has all required keys."""
        # Act
        context = build_critic_context("Name", "Plan", "Subject", "Body")

        # Assert
        required_keys = {
            "customer_name",
            "plan_name",
            "email_subject",
            "email_body_preview",
        }
        assert set(context.keys()) == required_keys


# ============================================================================
# TEST: Logging Functions (log_node_entry, log_node_exit, log_metric)
# ============================================================================


class TestLoggingFunctions:
    """Tests for logging helper functions."""

    def test_log_node_entry_does_not_raise(self) -> None:
        """Happy path: log_node_entry executes without raising."""
        # Arrange & Act (should not raise)
        log_node_entry("generator_node", "corr_123", ["customer_id", "customer_data"])

    def test_log_node_entry_with_empty_state_keys(self) -> None:
        """Edge case: Empty state keys list."""
        # Arrange & Act (should not raise)
        log_node_entry("node", "corr_id", [])

    def test_log_node_exit_does_not_raise(self) -> None:
        """Happy path: log_node_exit executes without raising."""
        # Arrange & Act (should not raise)
        log_node_exit("generator_node", "corr_123", 1234.5, "success")

    def test_log_node_exit_with_different_status(self) -> None:
        """Edge case: Different status values."""
        # Arrange & Act (should not raise)
        for status in ["success", "failure", "partial", "timeout"]:
            log_node_exit("node", "corr_id", 100.0, status)

    def test_log_metric_does_not_raise(self) -> None:
        """Happy path: log_metric executes without raising."""
        # Arrange & Act (should not raise)
        log_metric("email_generation_time_ms", 150.5)

    def test_log_metric_with_tags(self) -> None:
        """Edge case: log_metric with tags dict."""
        # Arrange & Act (should not raise)
        log_metric(
            "email_generation_time_ms",
            150.5,
            {"customer_tier": "premium", "model": "gpt-4"},
        )

    def test_log_metric_with_zero_value(self) -> None:
        """Edge case: log_metric with zero value."""
        # Arrange & Act (should not raise)
        log_metric("some_count", 0.0)

    def test_log_metric_with_negative_value(self) -> None:
        """Edge case: log_metric with negative value (e.g., time delta)."""
        # Arrange & Act (should not raise)
        log_metric("time_drift_seconds", -5.2)

    @patch("app.agents.utils.logger")
    def test_log_node_entry_calls_logger_info(self, mock_logger: Mock) -> None:
        """Mocking: Verify logger.info is called."""
        # Act
        log_node_entry("test_node", "corr_id", ["key1"])

        # Assert
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args
        assert "test_node" in str(call_args)

    @patch("app.agents.utils.logger")
    def test_log_node_exit_calls_logger_info(self, mock_logger: Mock) -> None:
        """Mocking: Verify logger.info is called with duration."""
        # Act
        log_node_exit("test_node", "corr_id", 250.5, "success")

        # Assert
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args
        assert "test_node" in str(call_args)

    @patch("app.agents.utils.logger")
    def test_log_metric_calls_logger_info(self, mock_logger: Mock) -> None:
        """Mocking: Verify logger.info is called with metric name."""
        # Act
        log_metric("request_latency_ms", 42.0)

        # Assert
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args
        assert "request_latency_ms" in str(call_args)
