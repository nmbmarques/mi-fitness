"""QR code login."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx
from loguru import logger

from mi_fitness.const import SERVICE_SID_HEALTH, STS_HEALTH_URL, XIAOMI_QR_LOGIN_URL
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import async_sleep, extract_credentials, parse_mi_response


async def login_qr(
    http: RetryAsyncClient,
    token: AuthToken,
    *,
    qr_callback: Callable[[str, str], Awaitable[None]] | None = None,
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
) -> None:
    """Run the QR code login flow.

    Args:
        http: HTTP client.
        token: AuthToken to write to.
        qr_callback: Callback to display the QR code. Receives ``(qr_image_url, login_url)``.
        poll_interval: Long-polling interval (seconds).
        max_wait: QR scan timeout (seconds).

    Raises:
        AuthError: Failed to get the QR code, or the scan timed out.
    """
    logger.info("Starting QR code login")

    # Step 1: Get the QR code info
    qr_params = {
        "_qrsize": "480",
        "qs": f"%3Fsid%3D{SERVICE_SID_HEALTH}%26_json%3Dtrue",
        "callback": STS_HEALTH_URL,
        "_hasLogo": "false",
        "sid": SERVICE_SID_HEALTH,
        "serviceParam": "",
        "_locale": "zh_CN",
        "_dc": str(int(time.time() * 1000)),
    }
    resp = await http.get(XIAOMI_QR_LOGIN_URL, params=qr_params)
    resp.raise_for_status()
    qr_data = parse_mi_response(resp.text)

    qr_image_url = qr_data.get("qr", "")
    login_url = qr_data.get("loginUrl", "")
    long_polling_url = qr_data.get("lp", "")
    qr_timeout = qr_data.get("timeout", max_wait)

    if not qr_image_url or not long_polling_url:
        raise AuthError(f"Failed to get QR code: {qr_data}")

    # Tell the caller to display the QR code
    if qr_callback:
        await qr_callback(qr_image_url, login_url)
    else:
        logger.info("Scan the QR code with the Xiaomi account app to log in")
        logger.info("QR code image: {}", qr_image_url)
        if login_url:
            logger.info("Or open in a browser: {}", login_url)

    # Step 2: Long-poll until the code is scanned
    effective_timeout = min(float(qr_timeout), max_wait)
    poll_request_timeout = 60.0
    logger.debug(
        "QR long polling started: effective_timeout={}s, request_timeout={}s",
        f"{effective_timeout:.0f}",
        f"{poll_request_timeout:.0f}",
    )
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > effective_timeout:
            raise AuthError(
                f"QR code scan timed out ({effective_timeout:.0f}s); please request a new one"
            )

        try:
            # Call httpx.AsyncClient.get directly to bypass RetryAsyncClient's retries
            resp = await httpx.AsyncClient.request(
                http, "GET", long_polling_url, timeout=poll_request_timeout
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.warning("QR login polling was interrupted")
            raise
        except httpx.TimeoutException:
            logger.debug("Long poll timed out, still waiting...")
            continue
        except httpx.RequestError as e:
            logger.warning("Long poll request failed: {}", e)
            await async_sleep(poll_interval)
            continue

        if resp.status_code != 200:
            logger.debug("Long poll returned {}, still waiting...", resp.status_code)
            await async_sleep(poll_interval)
            continue

        break

    data = parse_mi_response(resp.text)
    logger.info("Scan succeeded, userId={}", data.get("userId"))

    # Step 3: Extract credentials
    await extract_credentials(http, data, token)
