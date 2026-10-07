import logging
from typing import List, Optional, Literal
from html.parser import HTMLParser
import bleach
import re
from pydantic import BaseModel
from better_profanity import profanity

from app.guardrails.input_guards import GuardRailResult

logger = logging.getLogger(__name__)


class OutputGuardRailConfig(BaseModel):
    """Configuration for output vaildation rules. After LLM genreated text"""

    min_subject_length: int = 5
    max_subject_length: int = 100
    min_body_length: int = 200
    max_body_length: int = 5000
    enable_profanity_check: bool = True
    enable_url_validation: bool = True
    approved_domains: List[str] = ["blenddrop.store"]


class OutputGuards:
    """
    Validate LLM-generated email content.

    PYTHON CONCEPT: Instance vs Class Attributes
    - config: Shared across all instances
    - Each check method is independent and stateless
    """

    config: OutputGuardRailConfig = OutputGuardRailConfig()

    BANNED_PHRASES = [
        "click here to remove",
        "verify your password",
        "update billing information",
        "confirm your identity",
    ]

    ALLOWED_HTML_TAGS = {
        "p",
        "br",
        "strong",
        "em",
        "u",
        "a",
        "h1",
        "h2",
        "h3",
        "ul",
        "ol",
        "li",
        "div",
        "span",
        "img",
        "table",
        "tr",
        "td",
        "th",
    }

    ALLOWED_ATTRIBUTES = {
        "a": ["href", "title"],
        "img": ["src", "alt", "width", "height"],
        "div": ["style"],
        "span": ["style"],
    }

    @classmethod
    def validate_subject_line(cls, subject: str) -> GuardRailResult:
        """
        Validate email subject line length and content.

        PYTHON CONCEPT: String Methods
        - .strip(): Remove whitespace from ends
        - len(): Get string length
        """
        violations = []
        subject_clean = subject.strip()

        if len(subject_clean) < cls.config.min_subject_length:
            violations.append(
                f"Subject too short: {len(subject_clean)} < {cls.config.min_subject_length}"
            )

        if len(subject_clean) > cls.config.max_body_lenght:
            violations.append(
                f"Subect too long: {len(subject_clean)} > {cls.config.max_subject_length}"
            )

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="MODERATE" if violations else "PASS",
            layer="output",
        )

    @classmethod
    def validate_body_length(cls, body: str) -> GuardRailResult:
        """Validate email body is reasonable length."""
        violations = []
        body_clean = body.strip()

        if len(body_clean) < cls.config.min_body_length:
            violations.append(
                f"Body too short: {len(body_clean)} < {cls.config.min_body_length}"
            )

        if len(body_clean) > cls.config.max_body_length:
            violations.append(
                f"Body too long: {len(body_clean)} > {cls.config.max_body_length}"
            )

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="MODERATE" if violations else "PASS",
            layer="output",
        )

    @classmethod
    def check_profanity(cls, text: str) -> GuardRailResult:
        """
        Check for profanity using better-profanity library.

        PYTHON CONCEPT: External Libraries
        - better-profanity: Pre-built library for profanity detection
        - Instead of writing regex ourselves, we use tested code
        - Install: pip install better-profanity
        """
        violations = []

        if not cls.config.enable_profanity_check:
            return GuardRailResult(
                passed=True,
                violations=[],
                severity="PASS",
                layer="output",
            )

        # Check if text contains profanity
        if profanity.contains_profanity(text):
            # Find and report which words are problematic
            censored = profanity.censor(text)
            violations.append(f"Profanity detected in output")

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="output",
        )

    @classmethod
    def check_banned_phrases(cls, text: str) -> GuardRailResult:
        """
        Check for company-specific banned phrases.

        PYTHON CONCEPT: Case-Insensitive String Matching
        - .lower() both strings before comparing
        - Protects against "Click Here", "CLICK HERE", "click here"
        """
        violations = []
        text_lower = text.lower()

        for phrase in cls.BANNED_PHRASES:
            if phrase in text_lower:
                violations.append(f"Banned phrase detected: '{phrase}'")

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="output",
        )

    @classmethod
    def detect_unreplaced_placeholders(cls, text: str) -> GuardRailResult:
        """
        Detect un-replaced template variables.

        PYTHON CONCEPT: Regex Groups
        - {{\w+}} matches: {{customer_name}}, {{email}}, etc
        - \w = word character (a-z, A-Z, 0-9, _)
        """
        violations = []

        # Jinja2 templates: {{variable}}
        jinja_pattern = r"\{\{[\w_]+\}\}"
        jinja_matches = re.findall(jinja_pattern, text)

        # Python templates: {variable}
        python_pattern = r"\{[\w_]+\}"
        python_matches = re.findall(python_pattern, text)

        if jinja_matches:
            violations.append(f"Un-replaced Jinja2 template vars: {jinja_matches}")

        if python_matches:
            violations.append(f"Un-replaced Python template vars: {python_matches}")

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="output",
        )

    @classmethod
    def sanitize_html(cls, html: str) -> GuardRailResult:
        """
        Sanitize HTML to prevent XSS attacks.

        PYTHON CONCEPT: HTML Sanitization
        - bleach.clean(): Remove dangerous tags/attributes
        - Prevents: <script>, onclick=, onerror=, etc
        """
        violations = []

        if not cls.config.enable_html_validation:
            return GuardRailResult(
                passed=True,
                violations=[],
                severity="PASS",
                layer="output",
            )

        try:
            cleaned_html = bleach.clean(
                html,
                tags=cls.ALLOWED_HTML_TAGS,
                attributes=cls.ALLOWED_ATTRIBUTES,
                strip=True,
            )

            if len(cleaned_html) < len(html) * 0.95:
                violations.append("HTML contained dangerous (XSS prevention)")

            if "<script" in cleaned_html.lower():
                violations.append("Script tags detected after sanitization")

        except Exception as e:
            violations.append(f"HTML parsing error: {str(e)}")

        return GuardRailResult(
            passed=len(violations) == 0,
            violations=violations,
            severity="CRITICAL" if violations else "PASS",
            layer="output",
        )

    @classmethod
    async def validate_generated_email(cls, subject: str, body: str) -> GuardRailResult:
        """
        Comprehensive validation of generated email.

        PYTHON CONCEPT: Aggregating Results
        - Run multiple checks independently
        - Combine results with max severity
        - Returns comprehensive violation list
        """
        all_violations = []
        max_severity = "PASS"

        # Run all checks
        checks = [
            cls.validate_subject_line(subject),
            cls.validate_body_length(body),
            cls.check_profanity(body),
            cls.check_banned_phrases(body),
            cls.detect_unreplaced_placeholders(subject + " " + body),
            cls.sanitize_html(body),
        ]

        # Aggregate results
        for check_result in checks:
            all_violations.extend(check_result.violations)

            # Update severity to highest found
            severity_order = {"PASS": 0, "MINOR": 1, "MODERATE": 2, "CRITICAL": 3}
            if severity_order[check_result.severity] > severity_order[max_severity]:
                max_severity = check_result.severity

        logger.info(
            f"Output validation: {len(all_violations)} violations, severity={max_severity}"
        )

        return GuardRailResult(
            passed=len(all_violations) == 0,
            violations=all_violations,
            severity=max_severity,  # type: ignore
            layer="output",
        )
