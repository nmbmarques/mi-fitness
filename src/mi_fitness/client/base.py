"""Base layer for RC4-encrypted requests."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from mi_fitness.const import (
    DEFAULT_USER_AGENT,
    ERR_NOT_RELATIVES,
    ERR_NOT_SHARED_DATA_TYPE,
    HEALTH_API_BASE,
    REGION_TAG,
)
from mi_fitness.crypto import build_encrypted_params, decrypt_response
from mi_fitness.exceptions import (
    APIError,
    AuthError,
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    TokenExpiredError,
)
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken


def _coerce_api_code(value: Any, default: int = -1) -> int:
    """Best-effort handling of business codes given as int or str."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_api_message(result: dict[str, Any]) -> str:
    """Get the error message, handling different field names."""
    for key in ("message", "msg", "desc", "description"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "Unknown error"


def _is_time_scope_error(message: str) -> bool:
    """Detect 'outside the relative's shared time range' errors."""
    normalized = message.strip().lower()
    return "time out of data shared time scope" in normalized


def _extract_requested_data_type(params: dict[str, Any] | None) -> str:
    """Extract the requested data type key from the business parameters."""
    if not isinstance(params, dict):
        return ""
    key = params.get("key")
    return str(key) if key is not None else ""


def _build_auth_cookies(token: AuthToken) -> dict[str, str]:
    """Build the auth cookies required by the health API."""
    return {
        "cUserId": token.c_user_id,
        "serviceToken": token.service_token,
    }


async def _send_encrypted_http_request(
    http: RetryAsyncClient,
    method: str,
    url: str,
    enc_params: dict[str, Any],
    cookies: dict[str, str],
):
    """Send an encrypted request using the given HTTP method."""
    if method.upper() == "GET":
        return await http.get(url, params=enc_params, cookies=cookies)
    return await http.post(url, data=enc_params, cookies=cookies)


def _raise_for_http_status(resp: Any, method: str, path: str) -> None:
    """Convert an HTTP status code into an SDK exception."""
    if resp.status_code == 401:
        raise TokenExpiredError(f"Authentication expired: {method} {path} -> 401")
    if resp.status_code != 200:
        raise APIError(
            f"API request failed: {method} {path} -> {resp.status_code}",
            status_code=resp.status_code,
            response_body=resp.text,
        )


def _decrypt_result(ssecurity: str, nonce: str, resp: Any) -> dict[str, Any]:
    """Decrypt and validate the response body."""
    try:
        result = decrypt_response(ssecurity, nonce, resp.text)
    except Exception as e:
        raise APIError(
            f"Failed to decrypt response: {e}",
            status_code=resp.status_code,
            response_body=resp.text[:200],
        ) from e

    if not isinstance(result, dict):
        raise APIError(
            f"Decrypted response is not a JSON object: {type(result)}",
            response_body=str(result)[:200],
        )
    return result


def _raise_for_business_code(
    code: int,
    result: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
) -> NoReturn:
    """Map business error codes to SDK exceptions."""
    msg = _extract_api_message(result)
    body = json.dumps(result, ensure_ascii=False)

    if code == ERR_NOT_RELATIVES:
        raise FamilyMemberNotFoundError(f"Not a relative (code={code}): {msg}")

    if code == ERR_NOT_SHARED_DATA_TYPE:
        data_type = _extract_requested_data_type(params)
        suffix = f", key={data_type}" if data_type else ""
        if _is_time_scope_error(msg):
            raise DataOutOfSharedTimeScopeError(
                f"Outside the relative's shared time range (code={code}{suffix}): {msg}",
                data_type=data_type,
            )
        raise DataNotSharedError(
            f"Data type not shared (code={code}{suffix}): {msg}",
            data_type=data_type,
        )

    raise APIError(
        f"API business error (code={code}): {msg}",
        code=code,
        response_body=body,
    )


def create_api_http() -> RetryAsyncClient:
    """Create an HTTP client dedicated to API requests."""
    return RetryAsyncClient(
        timeout=30.0,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "region_tag": REGION_TAG,
            "handleparams": "true",
        },
    )


async def encrypted_request(
    http: RetryAsyncClient,
    token: AuthToken,
    method: str,
    path: str,
    base_url: str = HEALTH_API_BASE,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an RC4-encrypted API request and decrypt the response.

    Args:
        http: HTTP client.
        token: Logged-in AuthToken.
        method: HTTP method (GET / POST).
        path: API path.
        base_url: API base URL.
        params: Business parameters.

    Returns:
        The decrypted response JSON dict.

    Raises:
        APIError: The request or decryption failed.
        AuthError: Not currently logged in.
        TokenExpiredError: 401, authentication expired.
        FamilyMemberNotFoundError: Not a relative.
        DataNotSharedError: The relative has not shared the requested data type.
        DataOutOfSharedTimeScopeError: The requested date is outside the relative's shared time range.
    """
    if not token.service_token or not token.ssecurity:
        raise AuthError("Not logged in; call auth.login() first")

    ssecurity = token.ssecurity
    enc_params = build_encrypted_params(method, path, ssecurity, params)
    nonce = enc_params["_nonce"]
    cookies = _build_auth_cookies(token)
    url = base_url.rstrip("/") + path
    resp = await _send_encrypted_http_request(http, method, url, enc_params, cookies)
    _raise_for_http_status(resp, method, path)
    result = _decrypt_result(ssecurity, nonce, resp)

    code = _coerce_api_code(result.get("code"), default=-1)
    if code != 0:
        _raise_for_business_code(code, result, params=params)

    return result
