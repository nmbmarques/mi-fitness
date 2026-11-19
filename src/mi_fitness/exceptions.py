"""Custom exceptions."""


class MiSDKError(Exception):
    """Base MiSDK exception."""


class AuthError(MiSDKError):
    """Authentication error (login failure, expired token, etc.)."""


class APIError(MiSDKError):
    """The API request returned an unexpected result.

    Attributes:
        status_code: HTTP status code.
        code: Business error code (``result["code"]``; only set for business-level errors).
        response_body: Raw response body.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: int = 0,
        response_body: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.response_body = response_body

    def __repr__(self) -> str:
        return f"APIError(status_code={self.status_code}, code={self.code}, message={str(self)!r})"


class DeviceUntrustedError(AuthError):
    """Device not trusted; an SMS verification code is needed to complete login.

    Raised when a new device logs in for the first time (``securityStatus != 0``) and identity
    must be verified with an SMS code. Handle it automatically with ``login(verification_code_handler=...)``,
    or manually call ``send_verification_code()`` +
    ``login_with_verification_code()``.

    Attributes:
        security_status: Security status code returned by the server.
    """

    def __init__(self, message: str, *, security_status: int = 0):
        super().__init__(message)
        self.security_status = security_status


class CaptchaRequiredError(AuthError):
    """Image captcha risk control triggered; a human must solve it.

    During login the server may require an image captcha (error code 87001).
    Handle it automatically with ``login(captcha_handler=...)``,
    or catch this exception, download the captcha image from ``captcha_url`` yourself and retry.

    Attributes:
        captcha_url: Full URL of the captcha image.
    """

    def __init__(self, message: str, *, captcha_url: str = ""):
        super().__init__(message)
        self.captcha_url = captcha_url


class TokenExpiredError(AuthError):
    """Token has expired; log in again."""


class DataNotSharedError(MiSDKError):
    """The relative has not shared the requested data type."""

    def __init__(self, message: str, *, data_type: str = ""):
        super().__init__(message)
        self.data_type = data_type


class DataOutOfSharedTimeScopeError(DataNotSharedError):
    """The requested date is outside the time range the relative allows to be shared."""


class FamilyMemberNotFoundError(MiSDKError):
    """The specified relative could not be found."""
