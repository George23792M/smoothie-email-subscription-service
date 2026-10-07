class CustomerNotFoundException(Exception):
    """Raised when a customer record does not exist in the database"""

    def __init__(
        self, customer_id: str, error_message: str = "Customer record not found."
    ):
        self.customer_id = customer_id
        self.error_message = error_message
        super().__init__(self.error_message)
