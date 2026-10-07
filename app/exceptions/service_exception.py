class ServiceException(Exception):
    """Base exception for application level errors"""

    def __init__(self, error_message: str):
        self.error_message = error_message
        super().__init__(error_message)
