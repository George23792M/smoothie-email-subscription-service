import logging
import re
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr
from app.schemas.responses import CustomerDetailResponse

logger = logging.getLogger(__name__)


class GuardRailResult(BaseModel):
    """
    Structured result from any guard-rail check
    """

    passed: bool
    violations: List[str]
    severity: Literal["CRITICAL", "MODERATE", "MINOR", "PASS"]
    layer: str  # "input", "output", "final"
    details: Optional[dict] = None  # Extra data, optional


class InputGuardrailConfig(BaseModel):
    """
    Configuration for input guardrail rules.
    """

    max_name_length: int = 100
    min_name_length: int = 1
    max_email_length: int = 254
    min_password_age_minutes: int = 15  # Registartions older than this are skipped
    enable_sql_injection_check: bool = True
    enable_pii_detection: bool = True


# == Input Guardrails Rules ===


class InputGuards:
    """
    Container class for all input validation rules.

    PYTHON CONCEPT: Class Methods vs Instance Methods
    - @classmethod: Doesn't need instance, works on class level (like static in other languages)
    - Good for utility functions that don't maintain state
    """

    config: InputGuardrailConfig = InputGuardrailConfig()

    # SQL Injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\bselect\b|\bunion\b|\bdrop\b|\binsert\b|\bupdate\b|\bdelete\b)",
        r"(--|;|\'|\"|\/\*|\*\/)",  # SQL comment/quote chars
        r"(\bor\b\s+1\s*=\s*1)",  # Classic SQL injection
        r"(\bexec\b|\bexecute\b)",  # Execution commands
    ]

    # PII patterns (Social Security Number, Credit Card, etc)
    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",  # 123-45-6789
        "credit_card": r"\b\d{13,19}\b",  # 13-19 digit sequences
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # 123-456-7890
        "dob": r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/\d{4}\b",  # MM/DD/YYYY
    }

    @classmethod
    def validate_email_format(cls, email: str) -> GuardRailResult:
        """
        Validate email format.

        PYTHON CONCEPT: Type Hints with str and GuardrailResult
        - Function signature documents expected input/output
        - IDE can autocomplete and catch type errors
        """
        violations = []

        # Pydantic's EmailStr validator
        try:
            EmailStr.validate(email)
        except Exception:
            violations.append(f"Invalid email format: {email}")

        # Length check
        if len(email) > cls.config.max_email_length:
            violations.append(
                f"Email too long: {len(email)} > {cls.config.max_email_length}"
            )

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="input",
        )

    @classmethod
    def validate_name(cls, name: str, field_name: str = "name") -> GuardRailResult:
        """
        Validate customer name for length and suspicious patterns.

        PYTHON CONCEPT: Optional Parameters with Default Values
        - field_name="name" is the default parameter
        - Can be overridden: validate_name("John", field_name="first_name")
        """
        violations = []
        name_stripped = name.strip()

        if len(name_stripped) < cls.config.min_name_length:
            violations.append(f"{field_name} is empty")

        if len(name_stripped) > cls.config.max_name_length:
            violations.append(
                f"{field_name} too long: {len(name_stripped)} > {cls.config.max_name_length}"
            )

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="MODERATE" if violations else "PASS",
            layer="input",
        )

    @classmethod
    def detect_sql_injection(cls, value: str) -> GuardRailResult:
        """
        Detect SQL injection patterns in input.

        PYTHON CONCEPT: Regular Expressions (regex)
        - re.IGNORECASE: Match regardless of case
        - Pattern matching for security threats
        """
        violations = []

        if not cls.config.enable_sql_injection_check:
            return GuardRailResult(
                passed=True,
                violations=[],
                severity="PASS",
                layer="input",
            )

        value_lower = value.lower()

        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_lower, re.IGNORECASE):
                violations.append(f"Potential SQL injection: {pattern}")
                break  # Report first match

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="input",
        )

    @classmethod
    def detect_pii(cls, value: str) -> GuardRailResult:
        """
        Detect personally identifiable information.

        PYTHON CONCEPT: Dictionary Iteration
        - for pii_type, pattern in dict.items()
        - Flexible way to check multiple patterns
        """
        violations = []

        if not cls.config.enabled_pii_detections:
            return GuardRailResult(
                passed=True, violations=[], severity="PASS", layer="input"
            )

        for pii_type, pattern in cls.PII_PATTERNS.items():
            if re.search(pattern, value, re.IGNORECASE):
                violations.append(f"Detected {pii_type} in input")

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="MODERATE" if violations else "PASS",
            layer="input",
        )

    @classmethod
    def validate_customer_data(
        cls, customer_data: CustomerDetailResponse
    ) -> GuardRailResult:
        """
        Comprehensive validation of customer data.

        PYTHON CONCEPT: Async/Await
        - async def: This function can be paused (doesn't block)
        - await: "Wait for this operation to complete"
        - Use when: waiting for database, API, I/O operations
        """
        all_violations = []
        max_severity = "PASS"

        # validate email
        email_result = cls.validate_email_format(customer_data.email)
        all_violations.extend(email_result.violations)
        if email_result.serverity in ["CRITICAL", "MODERATE"]:
            max_severity = email_result.serverity

        # validate first name
        if customer_data.first_name:
            name_result = cls.validate_name(
                customer_data.first_name, field_name="first_name"
            )
            all_violations.extend(name_result.violations)

            # SQL injection check on name
            sql_result = cls.detect_sql_injection(customer_data.first_name)
            all_violations.extend(sql_result.violations)
            if sql_result.serverity == "CRITICAL":
                max_severity = "CRITICAL"

        # validate last name
        if customer_data.last_name:
            name_result = cls.validate_name(
                customer_data.last_name, field_name="last_name"
            )
            all_violations.extend(name_result.violations)

            # SQL injection check on last name
            sql_result = cls.detect_sql_injection(
                customer_data.last_name, field="last_name"
            )
            all_violations.extend(sql_result.violations)
            if sql_result.serverity == "CRITICAL":
                max_severity = "CRITICAL"

        # PII detection on all fields:
        for field_value in [
            customer_data.first_name,
            customer_data.last_name,
            customer_data.preferred_name,
            customer_data.email,
        ]:
            if field_value:
                pii_result = cls.detect_pii(field_value)
                all_violations.extend(pii_result.violations)

        logger.info(
            f"Input validation: {len(all_violations)}, violations, severity={max_severity}"
        )

        return GuardRailResult(
            passed=len(all_violations) == 0,
            violations=all_violations,
            severity=max_severity,
            layer="input",
            details={"customer_id": customer_data.customer_id},
        )
