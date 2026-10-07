"""
Deterministic validation checks for critic evaluation.

These are pure functions that check structural/compliance issues.
Supports four severity levels:
- CRITICAL: Compliance/safety violations (PII, phishing, medical claims)
- MODERATE: Quality issues (length, formatting, placeholder leakage)
- MINOR: Small improvements
- PASS: No issues
"""

import re
from typing import List, Tuple, Literal

# ============================================================================
# CONSTANTS
# ============================================================================

BANNED_PHRASES = [
    "click here to remove",
    "verify your password",
    "update billing information",
    "confirm your identity",
    "click here",
    "verify password",
    "confirm identity",
    "confirm your password",
    "remove your account",
]

MEDICAL_KEYWORDS = [
    "cure",
    "heal",
    "treat diagnosis",
    "disease medication",
    "prescription",
]

PII_PATTERNS = {
    "email_pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "customer_id": r"\bcust[_-]?\d+\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
}


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================


def check_subject_length(subject: str) -> Tuple[bool, str | None]:
    """
    Check subject line length (5-100 chars).

    Returns:
        (passed: bool, issue: str or None)
    """
    length = len(subject)
    if length < 5:
        return False, f"Subject too short ({length} chars, min is 5)"
    if length > 100:
        return False, f"Subject too long ({length} chars, max 100)"
    return True, None


def check_body_length(body: str) -> Tuple[bool, str | None]:
    """
    Check body length (50-2000 chars).

    Returns:
        (passed: bool, issue: str or None)
    """
    length = len(body)
    if length < 50:
        return False, f"Body too short ({length} chars, min 50)"
    if length > 2000:
        return False, f"Body too long ({length} chars, max 2000)"
    return True, None


def check_placeholder_leakage(text: str) -> Tuple[bool, str | None]:
    """
    Check for unreplaced placeholders ({{var}} or {var}).

    Returns:
        (passed: bool, issue: str or None)
    """
    matches = re.findall(r"\{\{[^}]+\}\}|\{[^}]+\}", text)
    if matches:
        return False, f"Unreplaced placeholders found: {', '.join(matches[:3])}"
    return True, None


def check_html_markdown_in_email(body: str) -> Tuple[bool, str | None]:
    """
    Check for HTML tags or Markdown syntax (should be plain text).

    Returns:
        (passed: bool, issue: str or None)
    """
    html_tags = re.findall(r"<[^>]+>", body)
    if html_tags:
        return False, f"HTML tags detected: {', '.join(html_tags[:3])}"

    # Markdown patterns (**, __, `, #, etc.)
    markdown_patterns = re.findall(
        r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|^#+\s|^\*+\s)", body, re.MULTILINE
    )
    if markdown_patterns:
        return False, f"Markdown syntax detected: {markdown_patterns[0]}"

    return True, None


def check_banned_phrases(subject: str, body: str) -> Tuple[bool, str | None]:
    """
    Check for banned phrases (phishing/scam indicators).

    Returns:
        (passed: bool, issue: str or None)
    """
    combined = (subject + " " + body).lower()
    for phrase in BANNED_PHRASES:
        if phrase in combined:
            return False, f"Banned phrase detected: '{phrase}'"
    return True, None


def check_pii_exposure(
    subject: str, body: str, safe_customer_id: str | None = None
) -> Tuple[bool, str | None]:
    """
    Check for sensitive personal information (PII) in email.

    Safe: customer_id (only if it matches safe_customer_id)
    Unsafe: email addresses, credit card, SSN, phone numbers, unauthorized customer IDs

    Args:
        subject: Email subject line
        body: Email body text
        safe_customer_id: The actual customer ID to allow (won't flag if found)

    Returns:
        (passed: bool, issue: str or None)
    """
    combined = subject + " " + body

    # Check for email addresses
    emails = re.findall(PII_PATTERNS["email_pattern"], combined)
    for email in emails:
        if not email.endswith("@smoothie.com"):
            return False, f"Email address exposed: {email}"

    # Check for customer IDs (unsafe unless it matches safe_customer_id)
    customer_ids = re.findall(PII_PATTERNS["customer_id"], combined, re.IGNORECASE)
    for cid in customer_ids:
        if safe_customer_id is None or cid.lower() != safe_customer_id.lower():
            return False, f"Unauthorized customer ID exposed: {cid}"

    # Check for credit card patterns
    if re.search(PII_PATTERNS["credit_card"], combined):
        return False, "Credit card information exposed"

    # Check for SSN patterns
    if re.search(PII_PATTERNS["ssn"], combined):
        return False, "SSN information exposed"

    # Check for phone patterns
    if re.search(PII_PATTERNS["phone"], combined):
        return False, "Phone number exposed"

    return True, None


def check_medical_claims(body: str) -> Tuple[bool, str | None]:
    """
    Check for unverifiable medical claims.

    Returns:
        (passed: bool, issue: str or None)
    """
    body_lower = body.lower()

    # Check for strong medical claims with cure/heal
    if "cure" in body_lower or "heal" in body_lower:
        return False, "Medical claim detected (cure/heal statements)"

    if "treat" in body_lower and "disease" in body_lower:
        return False, "Medical treatment claim detected"

    if "diagnose" in body_lower:
        return False, "Medical diagnosis claim detected"

    return True, None


def check_personalization_consistency(
    body: str,
    personalized_elements: List[str],
    preferred_name: str | None,
    first_name: str,
) -> Tuple[bool, str | None]:
    """
    Validate that personalized_elements claims match actual email content.

    Args:
        body: Email body text
        personalized_elements: List of personalization claims
        preferred_name: Customer preferred name (if any)
        first_name: Customer first name

    Returns:
        (passed: bool, issue: str or None)
    """
    if not personalized_elements:
        return True, None

    # Check if first_name_used is claimed but name isn't in body
    if "first_name_used" in personalized_elements:
        if first_name not in body:
            return (
                False,
                f"Claimed 'first_name_used' but '{first_name}' not found in body",
            )

    # Check if preferred_name_used is claimed but name isn't in body
    if "preferred_name_used" in personalized_elements and preferred_name:
        if preferred_name not in body:
            return (
                False,
                f"Claimed 'preferred_name_used' but '{preferred_name}' not found in body",
            )

    # Check if plan mentioned
    if "plan_name_mentioned" in personalized_elements:
        if "plan" not in body.lower():
            return False, "Claimed 'plan_name_mentioned' but no plan reference found"

    return True, None


# ============================================================================
# BATCH VALIDATION ORCHESTRATOR
# ============================================================================


def run_deterministic_checks(
    subject: str,
    body: str,
    preferred_name: str | None,
    first_name: str,
    personalized_elements: List[str],
    safe_customer_id: str | None = None,
) -> Tuple[Literal["CRITICAL", "MODERATE", "MINOR", "PASS"], List[str]]:
    """
    Run all deterministic checks and return highest severity + all issues.

    Severity levels:
    - CRITICAL: Safety/compliance violations (PII, phishing, medical claims)
    - MODERATE: Quality/formatting issues (length, placeholders, HTML)
    - MINOR: Small improvements (none currently defined)
    - PASS: All checks passed

    Strategy: Check CRITICAL first, if found return immediately with CRITICAL.
    Otherwise continue with MODERATE checks.

    Args:
        subject: Email subject line
        body: Email body text
        preferred_name: Customer preferred name (optional)
        first_name: Customer first name
        personalized_elements: List of personalization flags
        safe_customer_id: Customer ID that's safe to appear in email

    Returns:
        (severity: str, issues: List[str])
    """
    critical_issues = []
    moderate_issues = []

    # ===== CRITICAL CHECKS (Safety/Compliance) =====

    # PII Exposure (CRITICAL)
    pii_passed, pii_issue = check_pii_exposure(subject, body, safe_customer_id)
    if not pii_passed:
        critical_issues.append(pii_issue)

    # Banned phrases (CRITICAL - phishing indicator)
    phrases_passed, phrases_issue = check_banned_phrases(subject, body)
    if not phrases_passed:
        critical_issues.append(phrases_issue)

    # Medical claims (CRITICAL)
    medical_passed, medical_issue = check_medical_claims(body)
    if not medical_passed:
        critical_issues.append(medical_issue)

    # If CRITICAL issues found, return early
    if critical_issues:
        return "CRITICAL", critical_issues

    # ===== MODERATE CHECKS (Quality/Formatting) =====

    # Subject length
    subject_passed, subject_issue = check_subject_length(subject)
    if not subject_passed:
        moderate_issues.append(subject_issue)

    # Body length
    body_passed, body_issue = check_body_length(body)
    if not body_passed:
        moderate_issues.append(body_issue)

    # Placeholder leakage
    placeholder_passed, placeholder_issue = check_placeholder_leakage(body)
    if not placeholder_passed:
        moderate_issues.append(placeholder_issue)

    # HTML/Markdown
    html_passed, html_issue = check_html_markdown_in_email(body)
    if not html_passed:
        moderate_issues.append(html_issue)

    # Personalization consistency
    personal_passed, personal_issue = check_personalization_consistency(
        body, personalized_elements, preferred_name, first_name
    )
    if not personal_passed:
        moderate_issues.append(personal_issue)

    # ===== DETERMINE FINAL SEVERITY =====

    if moderate_issues:
        return "MODERATE", moderate_issues

    return "PASS", []
