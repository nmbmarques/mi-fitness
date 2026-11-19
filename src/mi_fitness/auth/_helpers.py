"""Internal utility functions for the auth module."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING

from loguru import logger

from mi_fitness.const import DEFAULT_LOGIN_USER_AGENT
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient

if TYPE_CHECKING:
    from mi_fitness.models import AuthToken

_COOKIE_DOMAINS = ("xiaomi.com", "mi.com")


def parse_mi_response(text: str) -> dict:
    """Parse a Xiaomi API JSON response with the ``&&&START&&&`` prefix."""
    body = text
    if body.startswith("&&&START&&&"):
        body = body[len("&&&START&&&") :]
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise AuthError(f"Failed to parse response: {text[:200]}") from e


def create_login_http() -> RetryAsyncClient:
    """Create an HTTP client dedicated to the login flow."""
    return RetryAsyncClient(
        follow_redirects=False,
        timeout=30.0,
        headers={
            "User-Agent": DEFAULT_LOGIN_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )


def normalize_captcha_url(captcha_url: str) -> str:
    """Complete the image captcha URL."""
    if captcha_url.startswith("/"):
        return f"https://account.xiaomi.com{captcha_url}"
    return captcha_url


def set_cookie_for_domains(
    http: RetryAsyncClient,
    name: str,
    value: str,
) -> None:
    """Write a cookie to all Xiaomi login-related domains."""
    for domain in _COOKIE_DOMAINS:
        http.cookies.set(name, value, domain=domain)


async def extract_service_token(http: RetryAsyncClient, location: str) -> str:
    """Follow the login redirect and extract serviceToken from the response cookies.

    Args:
        http: HTTP client.
        location: Redirect URL returned by login.

    Returns:
        The serviceToken value.
    """
    resp = await http.get(location)
    service_token = ""
    for header_val in resp.headers.get_list("set-cookie"):
        if "serviceToken=" in header_val:
            match = re.search(r"serviceToken=([^;]+)", header_val)
            if match:
                service_token = match.group(1)
                break

    if not service_token:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(str(resp.headers.get("location", location)))
        qs = parse_qs(parsed.query)
        service_token = qs.get("serviceToken", [""])[0]

    if not service_token:
        service_token = str(http.cookies.get("serviceToken", "") or "")

    if not service_token:
        raise AuthError("Failed to obtain serviceToken")

    return service_token


async def extract_credentials(
    http: RetryAsyncClient,
    data: dict,
    token: "AuthToken",
) -> None:
    """Extract credentials from the login response and save them to the token.

    Args:
        http: HTTP client.
        data: JSON dict returned by the login endpoint.
        token: AuthToken instance to write to.
    """
    token.ssecurity = data["ssecurity"]
    token.user_id = str(data.get("userId", ""))
    token.pass_token = data.get("passToken", "")
    token.c_user_id = data.get("cUserId", "")

    location = data.get("location", "")
    if location:
        service_token = await extract_service_token(http, location)
        token.service_token = service_token

    logger.debug(
        "Credentials extracted, ssecurity={}, user_id={}",
        token.ssecurity[:8] + "...",
        token.user_id,
    )


async def async_sleep(seconds: float) -> None:
    """Async sleep, wrapped so it is easy to mock in tests."""
    await asyncio.sleep(seconds)
