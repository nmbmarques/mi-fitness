"""Tests for the exception classes (exceptions.py)."""

from __future__ import annotations

from mi_fitness.exceptions import (
    APIError,
    AuthError,
    CaptchaRequiredError,
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    MiSDKError,
    TokenExpiredError,
)


class TestExceptionHierarchy:
    """Exception inheritance tests."""

    def test_base_exception(self) -> None:
        e = MiSDKError("test")
        assert str(e) == "test"
        assert isinstance(e, Exception)

    def test_auth_error_inherits(self) -> None:
        e = AuthError("auth fail")
        assert isinstance(e, MiSDKError)

    def test_token_expired_inherits_auth(self) -> None:
        e = TokenExpiredError("expired")
        assert isinstance(e, AuthError)
        assert isinstance(e, MiSDKError)

    def test_api_error_attributes(self) -> None:
        e = APIError(
            "api fail",
            status_code=500,
            code=1001,
            response_body='{"error": true}',
        )
        assert isinstance(e, MiSDKError)
        assert e.status_code == 500
        assert e.code == 1001
        assert e.response_body == '{"error": true}'
        assert str(e) == "api fail"

    def test_api_error_defaults(self) -> None:
        e = APIError("msg")
        assert e.status_code == 0
        assert e.code == 0
        assert e.response_body == ""

    def test_family_member_not_found(self) -> None:
        e = FamilyMemberNotFoundError("Not found")
        assert isinstance(e, MiSDKError)

    def test_captcha_required_inherits_auth(self) -> None:
        e = CaptchaRequiredError("Captcha required")
        assert isinstance(e, AuthError)
        assert isinstance(e, MiSDKError)

    def test_captcha_required_url(self) -> None:
        url = "https://account.xiaomi.com/pass/getCode?icodeType=login"
        e = CaptchaRequiredError("Captcha risk control", captcha_url=url)
        assert e.captcha_url == url
        assert str(e) == "Captcha risk control"

    def test_captcha_required_default_url(self) -> None:
        e = CaptchaRequiredError("msg")
        assert e.captcha_url == ""

    def test_data_not_shared_error(self) -> None:
        e = DataNotSharedError("Not shared", data_type="heart_rate")
        assert isinstance(e, MiSDKError)
        assert e.data_type == "heart_rate"

    def test_time_scope_error_inherits_data_not_shared(self) -> None:
        e = DataOutOfSharedTimeScopeError("Out of range", data_type="steps")
        assert isinstance(e, DataNotSharedError)
        assert e.data_type == "steps"
