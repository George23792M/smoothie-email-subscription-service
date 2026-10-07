"""
Critic Agent - Email Quality Evaluation (Hybrid: Deterministic + Jev Classification).

Two-stage evaluation:
1. Deterministic checks (fast, rule-based)
   - PII exposure, phishing indicators, medical claims (CRITICAL)
   - Length, formatting, placeholders, HTML/Markdown (MODERATE)

2. Jev classification (ultra-fast, cost-effective)
   - Only called for MODERATE issues (saves cost for CRITICAL/PASS)
   - Provides quality scoring and routing recommendation

Exports:
- critic_node: Main LangGraph node function
- validations: Deterministic check functions
- jev_client: Jev classification client
"""

from app.agents.critic.node import critic_node
from app.agents.critic.validations import run_deterministic_checks
from app.agents.critic.jev_client import classify_email_with_jev

__all__ = [
    "critic_node",
    "run_deterministic_checks",
    "classify_email_with_jev",
]
