import logging
from typing import Optional

from app.services.db_pool import DatabasePool
from app.schemas.responses import CustomerDetailResponse
from app.exceptions.database_exception import DatabaseExecutionException
from app.exceptions.customer_exception import CustomerNotFoundException

logger = logging.getLogger(__name__)

FETCH_CUSTOMER_SUBSCRIPTION_QUERY = """

SELECT c.id AS customer_id, c.first_name, c.last_name, c.preferred_name, c.email, s.plan_name
FROM customers c
JOIN subscriptions s on c.id = s.customer_id
WHERE c.id = $1
"""


def normalize_text(value: Optional[str]) -> Optional[str]:
    """
    Normalize text by stripping whitespace and converting empty strings to None.

    Args:
        value: The text to normalize, or None

    Returns:
        Normalized text or None if input was None or became empty after stripping
    """

    if value is None:
        return None
    return value.strip() or None


def _build_customer_response(row: dict) -> CustomerDetailResponse:
    """
    Transform database row into a CustomerDetailResponse.

    This helper function separates data transformation logic from database access,
    making the main function easier to read.

    Args:
        row: Database row with customer and subscription data

    Returns:
        Structured CustomerDetailResponse object
    """
    return CustomerDetailResponse(
        customer_id=row["customer_id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        preferred_name=row["preferred_name"],
        email=row["email"],
        plan_name=row["plan_name"],
    )


async def fetch_customer_subscription_details_from_db(
    customer_id: str,
) -> CustomerDetailResponse:

    pool = await DatabasePool.get_pool()

    async with pool.acquire() as connection:
        try:
            row = await connection.fetchrow(
                FETCH_CUSTOMER_SUBSCRIPTION_QUERY, customer_id
            )
        except Exception as ex:
            logger.error("Database query error for customer %s", customer_id)
            raise DatabaseExecutionException() from ex

        if not row:
            raise CustomerNotFoundException(
                customer_id=customer_id,
                error_message=f"Customer record not found for customer id: {customer_id}",
            )

        return _build_customer_response(row)
