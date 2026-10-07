from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Literal


class CustomerDetailResponse(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    customer_name: str
    preferred_name: str | None = None
    email: Optional[EmailStr] = None
    plan_name: str | None = None
    error: str | None = None
    status: Literal["SUCCESS", "NOT_FOUND", "ERROR"] = "SUCCESS"


class EmailResponse(BaseModel):
    success: bool
    message: str
    provider: str
    message_id: str | None = (None,)
    correlation_id: str


class WorkflowResult(BaseModel):
    customer_name: str
    plan_name: str | None = None
    generated_content: str | None = None
    is_safe: bool = True
    retry_count: int = 0
    error_message: str | None = None
    messages: List[Any] = Field(default_factor=list)


class WorkflowResponse(BaseModel):
    result: WorkflowResult
