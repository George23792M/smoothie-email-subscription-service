class DatabaseExecutionException(Exception):
    """Raised when during an infrastructure or connection error occurs during database exection"""

    def __init__(self, error_message: str = "Database Execution failed."):
        self.error_message = error_message
        super().__init__(self.error_message)
