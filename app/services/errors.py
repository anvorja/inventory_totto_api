class DomainError(Exception):
    """Error de negocio con un código estable que el frontend puede interpretar."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, **extra: object) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ProductNotFoundError(NotFoundError):
    code = "product_not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class SessionClosedError(ConflictError):
    code = "session_closed"


class UnauthorizedError(DomainError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(DomainError):
    status_code = 403
    code = "forbidden"


class TooManyAttemptsError(DomainError):
    status_code = 429
    code = "too_many_attempts"


class PasswordChangeRequiredError(ForbiddenError):
    code = "password_change_required"
