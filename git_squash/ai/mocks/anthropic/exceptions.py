"""Mock exceptions for the Anthropic SDK."""

from typing import Optional, Dict, Any


class APIError(Exception):
    """Base exception for all Anthropic API errors."""
    
    def __init__(
        self,
        message: str,
        request_id: Optional[str] = None,
        code: Optional[str] = None,
        param: Optional[str] = None,
        type: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.code = code
        self.param = param
        self.type = type


class APIConnectionError(APIError):
    """Raised when unable to connect to the Anthropic API."""
    
    def __init__(self, message: str = "Connection error", **kwargs):
        super().__init__(message, **kwargs)


class APITimeoutError(APIConnectionError):
    """Raised when a request to the Anthropic API times out."""
    
    def __init__(self, message: str = "Request timed out", **kwargs):
        super().__init__(message, **kwargs)


class APIStatusError(APIError):
    """Raised when an API response has a non-success status code."""
    
    def __init__(
        self,
        message: str,
        *,
        response: Optional[Any] = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, request_id=request_id, **kwargs)
        self.response = response
        self.status_code = status_code


class RateLimitError(APIStatusError):
    """Raised when the API rate limit is exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        status_code: int = 429,
        **kwargs
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class AuthenticationError(APIStatusError):
    """Raised when authentication fails."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        status_code: int = 401,
        **kwargs
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class BadRequestError(APIStatusError):
    """Raised when the request is invalid."""
    
    def __init__(
        self,
        message: str = "Bad request",
        *,
        status_code: int = 400,
        **kwargs
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class NotFoundError(APIStatusError):
    """Raised when the requested resource is not found."""
    
    def __init__(
        self,
        message: str = "Resource not found",
        *,
        status_code: int = 404,
        **kwargs
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class InternalServerError(APIStatusError):
    """Raised when the API encounters an internal error."""
    
    def __init__(
        self,
        message: str = "Internal server error",
        *,
        status_code: int = 500,
        **kwargs
    ):
        super().__init__(message, status_code=status_code, **kwargs)


__all__ = [
    "APIError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "RateLimitError",
    "AuthenticationError",
    "BadRequestError",
    "NotFoundError",
    "InternalServerError",
]