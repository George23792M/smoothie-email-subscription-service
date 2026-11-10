"""Render the provisional welcome template with a strictly limited HTML policy."""

import html
import re
import unicodedata
from dataclasses import dataclass
from html.entities import html5

from app.schemas.responses import CustomerDetailResponse
from app.services.postgres_workflows import ActiveEmailTemplate

PLACEHOLDER = "{{first_name}}"
MAX_SUBJECT_LENGTH = 200
MAX_HTML_LENGTH = 65536
MAX_FIRST_NAME_LENGTH = 200
CONTAINER_TAGS = frozenset({"p", "strong", "em", "ul", "ol", "li"})
TAG_PATTERN = re.compile(r"</?(?:p|strong|em|ul|ol|li)>|<br\s*/?>")
ENTITY_PATTERN = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);")


class WelcomeTemplateError(ValueError):
    """Represent an unsafe or invalid welcome template or customer value."""


@dataclass(frozen=True)
class RenderedWelcome:
    """Hold the validated subject and HTML body for a welcome email."""

    subject: str
    html_body: str


def _validate_text(value: str, limit: int) -> None:
    """Reject oversized text, control characters, and unsupported braces."""
    if not isinstance(value, str) or len(value) > limit:
        raise WelcomeTemplateError("Invalid welcome text")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise WelcomeTemplateError("Invalid welcome text")
    remainder = value.replace(PLACEHOLDER, "")
    if "{" in remainder or "}" in remainder:
        raise WelcomeTemplateError("Invalid welcome placeholder")


def _validate_entity(entity: str) -> None:
    """Reject malformed, unknown, or control-bearing HTML character references."""
    name = entity[1:-1]
    if not name.startswith("#") and name + ";" not in html5:
        raise WelcomeTemplateError("Invalid HTML entity")
    if name.startswith("#") and len(name) > 10:
        raise WelcomeTemplateError("Invalid HTML entity")
    decoded = html.unescape(entity)
    if decoded == entity or any(
        unicodedata.category(char).startswith("C") or char in "{}"
        for char in decoded
    ):
        raise WelcomeTemplateError("Invalid HTML entity")
    if name.startswith("#"):
        base = 16 if name.startswith("#x") else 10
        digits = name[2:] if base == 16 else name[1:]
        if len(digits) > 8:
            raise WelcomeTemplateError("Invalid HTML entity")
        number = int(digits, base)
        if number == 0 or number > 0x10FFFF or 0xD800 <= number <= 0xDFFF:
            raise WelcomeTemplateError("Invalid HTML entity")
        if unicodedata.category(chr(number)).startswith("C"):
            raise WelcomeTemplateError("Invalid HTML entity")


def _validate_html_text(text: str) -> None:
    """Validate text between tags and its explicitly terminated entities."""
    if "<" in text or ">" in text:
        raise WelcomeTemplateError("Invalid welcome markup")
    parts = ENTITY_PATTERN.split(text)
    if any("&" in part for part in parts):
        raise WelcomeTemplateError("Invalid HTML entity")
    for match in ENTITY_PATTERN.finditer(text):
        _validate_entity(match.group())


def _validate_tag(tag: str, stack: list[str]) -> None:
    """Enforce exact allowed tags and strict nesting."""
    parent = stack[-1] if stack else None
    if tag.startswith("<br"):
        if parent in {"ul", "ol"}:
            raise WelcomeTemplateError("Invalid welcome markup")
        return
    name = tag[2:-1] if tag.startswith("</") else tag[1:-1]
    if name not in CONTAINER_TAGS:
        raise WelcomeTemplateError("Invalid welcome markup")
    if tag.startswith("</"):
        if not stack or stack.pop() != name:
            raise WelcomeTemplateError("Unbalanced welcome markup")
    else:
        if (name == "li") != (parent in {"ul", "ol"}):
            raise WelcomeTemplateError("Invalid welcome markup")
        if parent in {"p", "strong", "em"} and name not in {"strong", "em"}:
            raise WelcomeTemplateError("Invalid welcome markup")
        stack.append(name)


def _validate_markup(body: str) -> None:
    """Reject unsupported markup and require balanced container tags."""
    stack: list[str] = []
    position = 0
    for match in TAG_PATTERN.finditer(body):
        text = body[position:match.start()]
        _validate_html_text(text)
        if stack and stack[-1] in {"ul", "ol"} and text.strip():
            raise WelcomeTemplateError("Invalid welcome markup")
        _validate_tag(match.group(), stack)
        position = match.end()
    _validate_html_text(body[position:])
    if stack:
        raise WelcomeTemplateError("Unbalanced welcome markup")


def _first_name(template: ActiveEmailTemplate, customer: CustomerDetailResponse) -> str:
    """Validate the customer value only when a placeholder requires it."""
    if PLACEHOLDER not in template.subject and PLACEHOLDER not in template.html_body:
        return ""
    name = customer.first_name
    _validate_text(name, MAX_FIRST_NAME_LENGTH)
    if not name.strip() or "{" in name or "}" in name:
        raise WelcomeTemplateError("Invalid welcome customer name")
    return name


def render_welcome(
    template: ActiveEmailTemplate, customer: CustomerDetailResponse
) -> RenderedWelcome:
    """Validate and render the approved first-name-only welcome template."""
    _validate_text(template.subject, MAX_SUBJECT_LENGTH)
    _validate_text(template.html_body, MAX_HTML_LENGTH)
    _validate_markup(template.html_body)
    name = _first_name(template, customer)
    subject = template.subject.replace(PLACEHOLDER, name)
    body = template.html_body.replace(PLACEHOLDER, html.escape(name, quote=True))
    _validate_text(subject, MAX_SUBJECT_LENGTH)
    _validate_text(body, MAX_HTML_LENGTH)
    return RenderedWelcome(subject=subject, html_body=body)
