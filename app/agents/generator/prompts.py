"""
Modular prompt rendering for email generation agents.

This module implements a three-part prompt architecture:
1. System Prompt: Static role, tone, safety rules (reused by all agents)
2. Task Prompt: Static task-specific instructions (welcome-specific)
3. Runtime Data: Customer context injected programmatically at generation time

Architecture Benefits:
- Single source of truth for safety rules across all email agents
- Easy reuse of system prompt for Generator, Critic, Refiner agents
- Support for A/B testing different system prompts without code changes
- Clean separation of concerns: what agents should do vs. what to work with

Example Usage:
    from app.agents.generator.prompts import render_generation_prompt, get_system_prompt

    customer_data = {
        "customer_id": "cust_123",
        "first_name": "Sarah",
        "preferred_name": "Sarah",
        "email": "sarah@example.com",
        "plan_name": "Premium",
        "signup_date": "2024-01-15"
    }

    # Render complete prompt (system + task + customer data)
    full_prompt = render_generation_prompt(customer_data)

    # Get system prompt for reuse in other agents
    system_rules = get_system_prompt()
"""

from typing import Any

# Load templates once at module import
_system_prompt_cache: str | None = None
_welcome_task_cache: str | None = None


def _load_system_prompt() -> str:
    """
    Load system prompt from disk (cached).

    System prompt contains:
    - Agent role and responsibilities
    - Tone and voice guidelines
    - Safety, privacy, and compliance rules
    - Forbidden content and language

    Static content with no variables. Reused by all email agents.

    Returns:
        str: System prompt text.

    Raises:
        FileNotFoundError: If system_prompt.txt not found in app/templates/email/.
    """

    global _system_prompt_cache

    if _system_prompt_cache is None:
        try:
            with open(
                "app/templates/email/system_prompt.txt", "r", encoding="utf-8"
            ) as f:
                _system_prompt_cache = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError("system_prompt.txt not found") from e
    return _system_prompt_cache


def _load_welcome_email_task_prompt() -> str:
    """
    Load welcome email task prompt from disk (cached).

    Task prompt contains:
    - Welcome-specific requirements and constraints
    - Content guidelines (what to include/exclude)
    - Output format specification
    - Examples of expected output

    Static content with no variables. Task-specific to welcome emails.

    Returns:
        str: Welcome task prompt text.

    Raises:
        FileNotFoundError: If welcome_email_task.txt not found in app/templates/email/.
    """

    global _welcome_task_cache

    if _welcome_task_cache is None:
        try:
            with open(
                "app/templates/email/welcome_email_task.txt", "r", encoding="utf-8"
            ) as f:
                _welcome_task_cache = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError("welcome_email_task.txt not found") from e
    return _welcome_task_cache


def _build_customer_data_section(customer_context: dict[str, Any]) -> str:
    """
    Build customer data section from runtime-provided context.

    This section is injected at generation time, separating static instructions
    from dynamic customer data. Makes it easy to trace which data was used.

    Args:
        customer_context: Dict containing customer information with keys:
            - customer_id (str): Unique customer identifier
            - first_name (str): Customer's first name
            - preferred_name (str): Customer's preferred greeting name (may be empty)
            - email (str): Customer's email address
            - plan_name (str): Name of subscription plan
            - signup_date (str): When customer subscribed (ISO format or similar)

    Returns:
        str: Formatted customer data section ready for inclusion in prompt.

    Example:
        >>> context = {
        ...     "customer_id": "cust_123",
        ...     "first_name": "Sarah",
        ...     "preferred_name": "Sarah",
        ...     "email": "sarah@example.com",
        ...     "plan_name": "Premium",
        ...     "signup_date": "2024-01-15"
        ... }
        >>> section = _build_customer_data_section(context)
        >>> assert "Premium" in section
    """
    customer_id = customer_context.get("customer_id", "N/A")
    first_name = customer_context.get("first_name", "N/A")
    preferred_name = customer_context.get("preferred_name", "")
    email = customer_context.get("email", "N/A")
    plan_name = customer_context.get("plan_name", "N/A")
    signup_date = customer_context.get("signup_date", "N/A")

    return f"""=== CUSTOMER DATA (INJECTED AT RUNTIME) ===
    customer_id: {customer_id}
    preferred_name: {preferred_name}
    first_name: {first_name}
    email: {email}
    plan_name: {plan_name}
    signup_date: {signup_date}"""


def render_generation_prompt(customer_context: dict[str, Any]) -> str:
    """
    Render complete prompt: System instructions + Task + Customer data.

    This is the main function called by generator_node() to build the full prompt
    for LLM consumption. It combines three components in order:

    1. System Prompt (static): Role, tone, safety/compliance rules
    2. Customer Data (dynamic): Runtime-injected customer information
    3. Task Prompt (static): Welcome-specific task and output format

    Separation Benefit:
    - System prompt can be reused by Critic, Refiner, and future agents
    - Customer data is clearly distinguished (runtime vs. static)
    - Changes to safety rules propagate to all agents automatically

    Args:
        customer_context: Dict containing customer information. See _build_customer_data_section()
            for required keys and format.

    Returns:
        str: Complete multi-part prompt ready for ChatOpenAI.invoke()

    Raises:
        FileNotFoundError: If system_prompt.txt or welcome_email_task.txt not found.

    Example:
        >>> customer = {
        ...     "customer_id": "cust_123",
        ...     "first_name": "Alex",
        ...     "preferred_name": "",
        ...     "email": "alex@example.com",
        ...     "plan_name": "Basic",
        ...     "signup_date": "2024-01-20"
        ... }
        >>> prompt = render_generation_prompt(customer)
        >>> assert "Basic" in prompt
        >>> assert "alex@example.com" in prompt
    """
    system = _load_system_prompt()
    customer = _build_customer_data_section(customer_context)
    task = _load_welcome_email_task_prompt()

    # Combine all parts with clear separators for debugging and tracing
    full_prompt = f"""{system} 
    {customer} 
    {task}"""

    return full_prompt


def get_system_prompt() -> str:
    """
    Get system prompt for reuse by other agents.

    Use this function when building Critic, Refiner, or future email agents
    (e.g., promotional, re-engagement). Ensures consistency: all agents follow
    the same role, tone, safety rules, and compliance guidelines.

    Returns:
        str: System prompt text.

    Raises:
        FileNotFoundError: If system_prompt.txt not found.

    Example:
        >>> system = get_system_prompt()
        >>> assert "safety" in system.lower() or "compliance" in system.lower()
    """
    return _load_system_prompt()


def get_welcome_task_prompt() -> str:
    """
    Get welcome email task prompt.

    Use for debugging, logging, or when building alternative prompt chains.
    Returns the static task instructions for welcome emails.

    Returns:
        str: Welcome email task prompt text.

    Raises:
        FileNotFoundError: If welcome_email_task.txt not found.

    Example:
        >>> task = get_welcome_task_prompt()
        >>> assert "REQUIREMENTS" in task
    """
    return _load_welcome_email_task_prompt()
