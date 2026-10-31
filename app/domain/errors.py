class DomainError(Exception):
    """A business rule said no. The API layer turns these into HTTP responses."""

    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    code = "not_found"


class InvalidAmount(DomainError):
    code = "invalid_amount"


class InsufficientFunds(DomainError):
    code = "insufficient_funds"


class UnbalancedTransaction(DomainError):
    code = "unbalanced_transaction"


class InvalidTransition(DomainError):
    code = "invalid_transition"


class EmailTaken(DomainError):
    code = "email_taken"


class InvalidCredentials(DomainError):
    code = "invalid_credentials"


class PermissionDenied(DomainError):
    code = "forbidden"


class SelfTransfer(DomainError):
    code = "self_transfer"


class IdempotencyConflict(DomainError):
    code = "idempotency_conflict"


class InvalidSignature(DomainError):
    code = "invalid_signature"
