import logging
from typing import Any
from jinja2 import Environment
from app.services.email.email_client import EmailClient
from app.schemas.responses import EmailResponse

logger = logging.getLogger(__name__)


class EmailService:

    def __init__(
        self, email_client: EmailClient, jinja_env: Environment, sender_email: str
    ):
        self._email_client = email_client
        self._jinja_env = jinja_env
        self._sender_email = sender_email

    def send_welcome_email(
        self,
        recipient_email: str,
        recipient_name: str,
        plan_name: str,
        dynamic_message: str,
    ) -> EmailResponse:
        try:
            html_content = self._render_welcome_template(
                recipient_name=recipient_name,
                plan_name=plan_name,
                dynamic_message=dynamic_message,
            )

            payload = self._build_email_payload(
                recipient_email=recipient_email,
                plan_name=plan_name,
                html_content=html_content,
            )

            response: EmailResponse = self._email_client.send(payload)

            if response.success:
                logger.info(
                    "Welcome email successfully sent to %s via %s [Correlation ID: %s, Message ID: %s]",
                    recipient_email,
                    response.provider,
                    response.correlation_id,
                    response.message_id,
                )
            else:
                logger.warning(
                    "Email provider returned failure for %s [Correlation ID: %s]: %s",
                    recipient_email,
                    response.correlation_id,
                    response.message,
                )
            return response

        except Exception as ex:
            logger.exception(
                "Unexpected error occurred when sending welcome email to %s",
                recipient_email,
            )
            return EmailResponse(
                success=False,
                message=f"Email sending failed exception: {str(ex)}",
                provider=self._email_client.provider_name,
                message_id=None,
                correlation_id="",
            )

    def _render_welcome_template(
        self, recipient_name: str, plan_name: str, dynamic_message: str
    ) -> str:
        template = self._jinja_env.get_template("welcome_email.html")
        return template.render(
            recipient_name=recipient_name,
            plan_name=plan_name,
            dynamic_message=dynamic_message,
        )

    def _build_email_payload(
        self, recipient_email: str, plan_name: str, html_content: str
    ) -> dict[str, Any]:
        return {
            "from": self._sender_email,
            "to": recipient_email,
            "subject": f"Welcome to Your {plan_name} Journey!",
            "html": html_content,
        }
