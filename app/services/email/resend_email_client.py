import resend
from app.schemas.responses import EmailResponse
from uuid import uuid4


class ResendEmailClient:

    def __init__(self, api_key: str) -> None:
        resend.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "Resend"

    def send(self, params: dict) -> EmailResponse:
        correlation_id = str(uuid4())
        try:
            response = resend.Emails.send(params)
            message_id = (
                response.get("id")
                if isinstance(response, dict)
                else getattr(response, "id", None)
            )

            return EmailResponse(
                success=True,
                message="Email dispatched successfully with Resend Channel",
                provider="Resend",
                message_id=message_id,
                correlation_id=correlation_id,
            )
        except Exception as e:
            return EmailResponse(
                success=False,
                message=f"Failed to send email via Resend: {str(e)}",
                provider="Resend",
                message_id=None,
                correlation_id=correlation_id,
            )
