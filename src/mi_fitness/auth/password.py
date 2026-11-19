"""Password login + SMS verification code flow."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from mi_fitness.const import (
    APP_NAME,
    ERR_DEVICE_UNTRUST,
    SERVICE_SID_HEALTH,
    XIAOMI_LOGIN_AUTH_URL,
    XIAOMI_LOGIN_URL,
    XIAOMI_PHONE_INFO_URL,
    XIAOMI_PREFERENCE_URL,
    XIAOMI_SEND_TICKET_URL,
    XIAOMI_TICKET_AUTH_URL,
)
from mi_fitness.exceptions import AuthError, CaptchaRequiredError, DeviceUntrustedError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import extract_credentials, normalize_captcha_url, parse_mi_response


# region Login page
async def get_login_page(
    http: RetryAsyncClient,
    *,
    login_sign: str = "",
) -> tuple[str, str]:
    """Request the login page to obtain _sign and callback.

    Args:
        http: HTTP client.
        login_sign: Login sign type. ``""`` for password login,
            ``"ticket"`` for SMS verification code login.

    Returns:
        A (sign, callback) tuple.
    """
    import re

    params: dict[str, str] = {
        "_json": "true",
        "appName": APP_NAME,
        "sid": SERVICE_SID_HEALTH,
        "_locale": "zh_CN",
    }
    if login_sign:
        params["_loginSign"] = login_sign

    resp = await http.get(XIAOMI_LOGIN_URL, params=params)
    resp.raise_for_status()

    body = resp.text
    if body.startswith("&&&START&&&"):
        body = body[len("&&&START&&&") :]

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        sign_match = re.search(r'"_sign"\s*:\s*"([^"]+)"', resp.text)
        callback_match = re.search(r'"callback"\s*:\s*"([^"]+)"', resp.text)
        sign = sign_match.group(1) if sign_match else ""
        callback = callback_match.group(1) if callback_match else ""
        return sign, callback

    sign = data.get("_sign", "")
    callback = data.get("callback", "")
    return sign, callback


# endregion


# region Password submission
async def submit_login(
    http: RetryAsyncClient,
    token: AuthToken,
    username: str,
    password: str,
    sign: str,
    callback: str,
) -> None:
    """Submit the password and handle the login response.

    On success writes the token directly; raises DeviceUntrustedError if the device is not trusted.

    Raises:
        AuthError: Wrong password.
        DeviceUntrustedError: Device not trusted; SMS verification required.
    """
    data = await _raw_submit_login(http, username, password, sign, callback)

    if data.get("ssecurity"):
        await extract_credentials(http, data, token)
        return

    if data.get("code") == ERR_DEVICE_UNTRUST:
        raise DeviceUntrustedError(
            f"Login requires two-step verification (code={ERR_DEVICE_UNTRUST}). Switching to the SMS verification code flow automatically.",
            security_status=16,
        )

    security_status = data.get("securityStatus", 0)
    if security_status != 0:
        raise DeviceUntrustedError(
            f"Device not trusted (securityStatus={security_status}); "
            f"an SMS verification code is required to complete login.\n"
            f"Pass a verification_code_handler callback, "
            f"or manually call send_verification_code() + "
            f"login_with_verification_code().",
            security_status=security_status,
        )

    keys = ", ".join(sorted(data.keys()))
    raise AuthError(
        f"Login error: password accepted but no credentials returned. Response fields: {keys}"
    )


async def _raw_submit_login(
    http: RetryAsyncClient,
    username: str,
    password: str,
    sign: str,
    callback: str,
) -> dict:
    """Submit the password to serviceLoginAuth2 and return the parsed response."""
    pwd_hash = hashlib.md5(password.encode()).hexdigest().upper()

    form_data = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_sign": sign,
        "callback": callback,
        "user": username,
        "hash": pwd_hash,
        "qs": f"%3Fsid%3D{SERVICE_SID_HEALTH}",
        "_locale": "zh_CN",
    }

    resp = await http.post(
        XIAOMI_LOGIN_AUTH_URL,
        data=form_data,
        headers={"Referer": XIAOMI_LOGIN_URL},
    )
    resp.raise_for_status()

    data = parse_mi_response(resp.text)

    code = data.get("code", -1)
    if code == ERR_DEVICE_UNTRUST:
        return data
    if code != 0:
        desc = data.get("desc", "Unknown error")
        raise AuthError(f"Login failed (code={code}): {desc}")

    return data


# endregion


# region SMS verification code
async def ensure_ticket_login_ready(http: RetryAsyncClient) -> None:
    """Request the preference page to prepare the ticket login context."""
    resp = await http.get(XIAOMI_PREFERENCE_URL, params={"_locale": "zh_CN"})
    resp.raise_for_status()
    data = parse_mi_response(resp.text)
    if data.get("code", -1) != 0:
        raise AuthError(
            f"Failed to initialise login preferences: {data.get('description', 'Unknown error')}"
        )


def _build_ticket_form_data(username: str, *, captcha_code: str = "") -> dict[str, str]:
    """Build the common form for SMS verification endpoints."""
    form_data: dict[str, str] = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_locale": "zh_CN",
        "user": username,
    }
    if captcha_code:
        form_data["captCode"] = captcha_code
    return form_data


async def _post_ticket_request(
    http: RetryAsyncClient,
    url: str,
    username: str,
    *,
    captcha_code: str = "",
    error_prefix: str,
) -> dict[str, Any]:
    """Submit an SMS verification request and handle captcha risk control uniformly."""
    resp = await http.post(
        url,
        data=_build_ticket_form_data(username, captcha_code=captcha_code),
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    if data.get("code", -1) == 0:
        return data

    desc = data.get("description", "Unknown error")
    captcha_url = normalize_captcha_url(data.get("captchaUrl", ""))
    if captcha_url:
        raise CaptchaRequiredError(
            f"{error_prefix}: image captcha risk control triggered (code={data.get('code')})",
            captcha_url=captcha_url,
        )
    raise AuthError(f"{error_prefix}: {desc}")


async def send_ticket(
    http: RetryAsyncClient,
    username: str,
    *,
    captcha_code: str = "",
) -> None:
    """Send an SMS verification code to the user's phone.

    Raises:
        CaptchaRequiredError: Image captcha risk control triggered.
        AuthError: Sending failed.
    """
    data = await _post_ticket_request(
        http,
        XIAOMI_SEND_TICKET_URL,
        username,
        captcha_code=captcha_code,
        error_prefix="Failed to send verification code",
    )

    logger.debug("Verification code sent, vCodeLen={}", data.get("data", {}).get("vCodeLen"))


async def get_phone_info(
    http: RetryAsyncClient,
    username: str,
    *,
    captcha_code: str = "",
) -> tuple[str, str]:
    """Get the phone number info and ticketToken.

    Returns:
        A (masked phone number, ticketToken) tuple.

    Raises:
        CaptchaRequiredError: Image captcha risk control triggered.
        AuthError: Request failed.
    """
    data = await _post_ticket_request(
        http,
        XIAOMI_PHONE_INFO_URL,
        username,
        captcha_code=captcha_code,
        error_prefix="Failed to get phone info",
    )

    info = data.get("data", {})
    phone = info.get("phone", "Unknown number")
    ticket_token = info.get("ticketToken", "")
    if not ticket_token:
        raise AuthError("Server did not return a ticketToken; cannot send verification code")
    return phone, ticket_token


async def fetch_captcha_image(http: RetryAsyncClient, captcha_url: str) -> bytes:
    """Download the image captcha."""
    logger.debug("Downloading image captcha: {}", captcha_url)
    resp = await http.get(captcha_url)
    resp.raise_for_status()
    return resp.content


async def submit_ticket_auth(
    http: RetryAsyncClient,
    token: AuthToken,
    code: str,
    sign: str,
    callback: str,
) -> None:
    """Complete serviceLoginTicketAuth login with the verification code.

    Args:
        http: HTTP client.
        token: AuthToken to write to.
        code: 6-digit SMS verification code entered by the user.
        sign: _sign obtained from the login page.
        callback: Callback URL.
    """
    form_data = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_sign": sign,
        "callback": callback,
        "ticket": code,
        "qs": (
            f"%3F_loginSign%3Dticket%26_json%3Dtrue%26sid%3D{SERVICE_SID_HEALTH}%26_locale%3Dzh_CN"
        ),
        "_locale": "zh_CN",
    }

    resp = await http.post(
        XIAOMI_TICKET_AUTH_URL,
        data=form_data,
        headers={"Referer": XIAOMI_LOGIN_URL},
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    code_val = data.get("code", -1)
    if code_val != 0:
        desc = data.get("desc", "Unknown error")
        raise AuthError(f"Verification code check failed (code={code_val}): {desc}")

    if not data.get("ssecurity"):
        raise AuthError("Verification code accepted but no credentials returned")

    await extract_credentials(http, data, token)


# endregion
