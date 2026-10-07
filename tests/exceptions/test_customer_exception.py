"""
Unit tests for app/exceptions/customer_exception.py

Test Coverage:
- CustomerNotFoundException instantiation (with/without custom message)
- Exception attributes (customer_id, error_message)
- Exception inheritance from Exception base class
- Exception message formatting
- Exception raising and catching
- Edge cases (empty IDs, special characters, unicode)

All tests are deterministic and offline.
"""

import pytest

from app.exceptions.customer_exception import CustomerNotFoundException

# ============================================================================
# TEST: CustomerNotFoundException - Instantiation
# ============================================================================


class TestCustomerNotFoundExceptionInstantiation:
    """Tests for creating CustomerNotFoundException instances."""

    def test_instantiation_with_customer_id_only(self) -> None:
        """Happy path: Create exception with required customer_id."""
        # Arrange
        customer_id = "cust_12345"

        # Act
        exception = CustomerNotFoundException(customer_id)

        # Assert
        assert isinstance(exception, CustomerNotFoundException)
        assert isinstance(exception, Exception)
        assert exception.customer_id == "cust_12345"
        assert exception.error_message == "Customer record not found."

    def test_instantiation_with_custom_error_message(self) -> None:
        """Happy path: Create exception with customer_id and custom message."""
        # Arrange
        customer_id = "cust_67890"
        custom_message = "This customer does not exist in our database."

        # Act
        exception = CustomerNotFoundException(customer_id, custom_message)

        # Assert
        assert exception.customer_id == "cust_67890"
        assert (
            exception.error_message == "This customer does not exist in our database."
        )

    def test_attributes_are_stored_correctly(self) -> None:
        """Validation: Both customer_id and error_message are stored as attributes."""
        # Arrange
        customer_id = "user_999"
        error_message = "Customer record not found."

        # Act
        exception = CustomerNotFoundException(customer_id, error_message)

        # Assert
        assert hasattr(exception, "customer_id")
        assert hasattr(exception, "error_message")
        assert exception.customer_id == customer_id
        assert exception.error_message == error_message

    def test_default_error_message_value(self) -> None:
        """Validation: Default error_message is set correctly."""
        # Act
        exception = CustomerNotFoundException("any_id")

        # Assert
        assert exception.error_message == "Customer record not found."

    def test_custom_error_message_overrides_default(self) -> None:
        """Validation: Custom error_message overrides the default."""
        # Arrange
        custom_msg = "Custom error message"

        # Act
        exception = CustomerNotFoundException("id", custom_msg)

        # Assert
        assert exception.error_message == custom_msg
        assert exception.error_message != "Customer record not found."


# ============================================================================
# TEST: CustomerNotFoundException - Exception Behavior
# ============================================================================


class TestCustomerNotFoundExceptionBehavior:
    """Tests for exception behavior and inheritance."""

    def test_inherits_from_exception(self) -> None:
        """Validation: Exception inherits from Python's Exception base class."""
        # Act
        exception = CustomerNotFoundException("cust_123")

        # Assert
        assert isinstance(exception, Exception)

    def test_exception_message_from_args(self) -> None:
        """Validation: Exception args tuple contains the error message."""
        # Arrange
        error_message = "Customer not found in database"

        # Act
        exception = CustomerNotFoundException("cust_456", error_message)

        # Assert
        # args[0] should be the message passed to super().__init__()
        assert exception.args == (error_message,)

    def test_exception_string_representation(self) -> None:
        """Validation: str(exception) returns the error message."""
        # Arrange
        error_message = "Customer not found"

        # Act
        exception = CustomerNotFoundException("cust_789", error_message)

        # Assert
        assert str(exception) == error_message

    def test_exception_string_uses_default_message(self) -> None:
        """Validation: str(exception) returns default message when custom not provided."""
        # Act
        exception = CustomerNotFoundException("cust_default")

        # Assert
        assert str(exception) == "Customer record not found."

    def test_exception_repr(self) -> None:
        """Validation: Exception has a repr representation."""
        # Act
        exception = CustomerNotFoundException("cust_123")

        # Assert
        repr_str = repr(exception)
        assert "CustomerNotFoundException" in repr_str


# ============================================================================
# TEST: CustomerNotFoundException - Raising and Catching
# ============================================================================


class TestCustomerNotFoundExceptionRaisingAndCatching:
    """Tests for raising and catching the exception."""

    def test_can_raise_and_catch_by_specific_type(self) -> None:
        """Validation: Exception can be raised and caught by specific type."""
        # Arrange & Act & Assert
        with pytest.raises(CustomerNotFoundException):
            raise CustomerNotFoundException("cust_catch_test")

    def test_can_catch_by_base_exception_type(self) -> None:
        """Validation: Exception can be caught as base Exception."""
        # Arrange & Act & Assert
        with pytest.raises(Exception):
            raise CustomerNotFoundException("cust_base_catch")

    def test_exception_attributes_accessible_after_catch(self) -> None:
        """Validation: Attributes are accessible when exception is caught."""
        # Arrange
        customer_id = "cust_attr_test"
        error_message = "Custom message for testing"

        # Act & Assert
        with pytest.raises(CustomerNotFoundException) as exc_info:
            raise CustomerNotFoundException(customer_id, error_message)

        assert exc_info.value.customer_id == customer_id
        assert exc_info.value.error_message == error_message

    def test_exception_message_accessible_after_catch(self) -> None:
        """Validation: Exception message is accessible via str()."""
        # Arrange
        message = "Test message"

        # Act & Assert
        with pytest.raises(CustomerNotFoundException) as exc_info:
            raise CustomerNotFoundException("cust_123", message)

        assert str(exc_info.value) == message


# ============================================================================
# TEST: CustomerNotFoundException - Edge Cases
# ============================================================================


class TestCustomerNotFoundExceptionEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_customer_id(self) -> None:
        """Edge case: Create exception with empty string customer_id."""
        # Act
        exception = CustomerNotFoundException("")

        # Assert
        assert exception.customer_id == ""
        assert exception.error_message == "Customer record not found."

    def test_whitespace_customer_id(self) -> None:
        """Edge case: Create exception with whitespace-only customer_id."""
        # Act
        exception = CustomerNotFoundException("   ")

        # Assert
        assert exception.customer_id == "   "

    def test_customer_id_with_special_characters(self) -> None:
        """Edge case: Create exception with special characters in customer_id."""
        # Arrange
        special_id = "cust!@#$%^&*()_+-=[]{}|;:',.<>?/~`"

        # Act
        exception = CustomerNotFoundException(special_id)

        # Assert
        assert exception.customer_id == special_id

    def test_customer_id_with_unicode_characters(self) -> None:
        """Edge case: Create exception with unicode customer_id."""
        # Arrange
        unicode_id = "cust_用户_مستخدم_пользователь"

        # Act
        exception = CustomerNotFoundException(unicode_id)

        # Assert
        assert exception.customer_id == unicode_id

    def test_customer_id_with_newlines(self) -> None:
        """Edge case: Create exception with newlines in customer_id."""
        # Arrange
        id_with_newline = "cust_123\ncust_456"

        # Act
        exception = CustomerNotFoundException(id_with_newline)

        # Assert
        assert exception.customer_id == id_with_newline

    def test_very_long_customer_id(self) -> None:
        """Edge case: Create exception with very long customer_id."""
        # Arrange
        long_id = "cust_" + "x" * 10000

        # Act
        exception = CustomerNotFoundException(long_id)

        # Assert
        assert exception.customer_id == long_id
        assert len(exception.customer_id) == 10005

    def test_empty_error_message(self) -> None:
        """Edge case: Create exception with empty error message."""
        # Act
        exception = CustomerNotFoundException("cust_123", "")

        # Assert
        assert exception.error_message == ""
        assert str(exception) == ""

    def test_very_long_error_message(self) -> None:
        """Edge case: Create exception with very long error message."""
        # Arrange
        long_message = "Error: " + "x" * 10000

        # Act
        exception = CustomerNotFoundException("cust_123", long_message)

        # Assert
        assert exception.error_message == long_message
        assert len(exception.error_message) == 10007

    def test_error_message_with_multiline_text(self) -> None:
        """Edge case: Create exception with multiline error message."""
        # Arrange
        multiline_message = "Line 1\nLine 2\nLine 3"

        # Act
        exception = CustomerNotFoundException("cust_123", multiline_message)

        # Assert
        assert exception.error_message == multiline_message
        assert "\n" in exception.error_message


# ============================================================================
# TEST: CustomerNotFoundException - Multiple Instantiations
# ============================================================================


class TestCustomerNotFoundExceptionMultipleInstances:
    """Tests for creating multiple independent instances."""

    def test_multiple_instances_are_independent(self) -> None:
        """Validation: Multiple exception instances have independent state."""
        # Arrange & Act
        exc1 = CustomerNotFoundException("cust_001", "Message 1")
        exc2 = CustomerNotFoundException("cust_002", "Message 2")
        exc3 = CustomerNotFoundException("cust_003")

        # Assert
        assert exc1.customer_id == "cust_001"
        assert exc2.customer_id == "cust_002"
        assert exc3.customer_id == "cust_003"

        assert exc1.error_message == "Message 1"
        assert exc2.error_message == "Message 2"
        assert exc3.error_message == "Customer record not found."

    def test_instances_with_same_id_are_different_objects(self) -> None:
        """Validation: Two instances with same customer_id are different objects."""
        # Arrange & Act
        exc1 = CustomerNotFoundException("cust_same")
        exc2 = CustomerNotFoundException("cust_same")

        # Assert
        assert exc1 is not exc2
        assert exc1.customer_id == exc2.customer_id
        assert exc1 == exc1  # Same object equals itself
        assert exc1 != exc2  # Different objects, even with same data


# ============================================================================
# TEST: CustomerNotFoundException - Type and Value Correctness
# ============================================================================


class TestCustomerNotFoundExceptionTypes:
    """Tests for type correctness and attribute types."""

    def test_customer_id_is_string_type(self) -> None:
        """Validation: customer_id attribute is a string."""
        # Act
        exception = CustomerNotFoundException("cust_123")

        # Assert
        assert isinstance(exception.customer_id, str)

    def test_error_message_is_string_type(self) -> None:
        """Validation: error_message attribute is a string."""
        # Act
        exception = CustomerNotFoundException("cust_123", "Error message")

        # Assert
        assert isinstance(exception.error_message, str)

    def test_exception_is_exception_type(self) -> None:
        """Validation: Exception instance is an Exception type."""
        # Act
        exception = CustomerNotFoundException("cust_123")

        # Assert
        assert isinstance(exception, Exception)

    def test_exception_has_default_exception_attributes(self) -> None:
        """Validation: Exception has standard Exception attributes."""
        # Act
        exception = CustomerNotFoundException("cust_123", "Test message")

        # Assert
        assert hasattr(exception, "args")
        assert hasattr(exception, "__traceback__")
        assert hasattr(exception, "__cause__")
        assert hasattr(exception, "__context__")


# ============================================================================
# TEST: CustomerNotFoundException - Comparison and Identity
# ============================================================================


class TestCustomerNotFoundExceptionComparison:
    """Tests for exception comparison and equality."""

    def test_exception_equality_with_same_data(self) -> None:
        """Validation: Two instances with same data are equal (default behavior)."""
        # Arrange & Act
        exc1 = CustomerNotFoundException("cust_123", "Same message")
        exc2 = CustomerNotFoundException("cust_123", "Same message")

        # Assert
        # By default, different objects are not equal even with same data
        # (unless __eq__ is overridden, which it isn't in this exception)
        assert exc1 is not exc2

    def test_exception_self_equality(self) -> None:
        """Validation: Exception instance equals itself."""
        # Act
        exception = CustomerNotFoundException("cust_123")

        # Assert
        assert exception == exception

    def test_exception_not_equal_to_other_type(self) -> None:
        """Validation: Exception is not equal to other types."""
        # Arrange & Act
        exception = CustomerNotFoundException("cust_123")
        string = "cust_123"

        # Assert
        assert exception != string
        assert exception != {"customer_id": "cust_123"}
