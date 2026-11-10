"""Tests for the provisional welcome template rendering contract."""

import pytest

from app.schemas.responses import CustomerDetailResponse
from app.services.email.welcome_renderer import WelcomeTemplateError, render_welcome
from app.services.postgres_workflows import ActiveEmailTemplate


def customer(name="Ada"):
    """Build synthetic customer data."""
    return CustomerDetailResponse(
        customer_id="synthetic", first_name=name, last_name="Example", customer_name="Example",
    )


def template(subject="Welcome", body="<p>Hello</p>"):
    """Build an active template for rendering."""
    return ActiveEmailTemplate(active=True, subject=subject, html_body=body)


def test_render_escapes_customer_html_and_preserves_subject_text():
    """Substitution escapes HTML text without changing ordinary subject text."""
    result = render_welcome(template("Hi {{first_name}}", "<p>Hi {{first_name}}</p>"),
                            customer('<script>"&</script>'))
    assert result.subject == 'Hi <script>"&</script>'
    assert result.html_body == "<p>Hi &lt;script&gt;&quot;&amp;&lt;/script&gt;</p>"


def test_unused_blank_name_is_allowed():
    """A template without a placeholder does not require a customer name."""
    assert render_welcome(template(), customer("")).html_body == "<p>Hello</p>"


@pytest.mark.parametrize("body", [
    "<script>alert(1)</script>", '<p onclick="x">Hello</p>',
    '<a href="https://example.test">link</a>', "<img src=x>", "<p>{{unknown}}</p>",
    "<p>{{ first_name }}</p>", "<p>{first_name}</p>", "<p><!--x--></p>",
    "<!doctype html>", "<p><strong>x</p></strong>", "<p>&#123;</p>",
    "<p>&#x0a;</p>", "<p>bad &entity;</p>", "<p>{{first_name}}</p>\n",
])
def test_render_rejects_unsafe_markup_placeholders_and_controls(body):
    """Disallowed HTML, entities, placeholders, and controls fail closed."""
    with pytest.raises(WelcomeTemplateError):
        render_welcome(template(body=body), customer())


@pytest.mark.parametrize("name", ["", " ", "name\nbcc", "{name}", "x" * 201])
def test_render_rejects_invalid_name_when_used(name):
    """A used customer value must be nonempty, bounded, and free of controls or braces."""
    with pytest.raises(WelcomeTemplateError):
        render_welcome(template(body="<p>{{first_name}}</p>"), customer(name))


def test_render_checks_subject_length_after_substitution():
    """A valid template cannot expand beyond the final subject limit."""
    with pytest.raises(WelcomeTemplateError):
        render_welcome(template(subject="x" * 180 + "{{first_name}}"), customer("A" * 21))


def test_render_accepts_final_subject_limit_exactly():
    """A subject of exactly 200 characters is accepted after substitution."""
    rendered = render_welcome(template(subject="x" * 180 + "{{first_name}}"), customer("A" * 20))
    assert len(rendered.subject) == 200
