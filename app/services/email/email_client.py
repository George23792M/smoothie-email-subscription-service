from typing import Protocol
from app.schemas.responses import EmailResponse


class EmailClient(Protocol):
    """
    Defines the capability requrired by EmailService.

    EmailService should be able to send email .
    It should NOT need to know which provider is
    Resend, SendGrid, AWS SES or mock implementation

    """

    @property
    def provider_name(self) -> str: ...

    def send(self, params: dict) -> EmailResponse: ...
