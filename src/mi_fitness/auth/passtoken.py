"""passToken exchange login."""

from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import quote

from loguru import logger

from mi_fitness.const import SERVICE_SID_HEALTH, XIAOMI_LOGIN_URL
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import extract_service_token, parse_mi_response, set_cookie_for_domains


async def login_passtoken(
    http: RetryAsyncClient,
    token: AuthToken,
    *,
    pass_token: str,
    user_id: str,
    device_id: str = "",
) -> None:
    """Exchange a passToken for full login credentials.

    Args:
        http: HTTP client.
        token: AuthToken to write to.
        pass_token: Xiaomi account passToken.
        user_id: Xiaomi account userId.
        device_id: Device identifier (optional).

    Raises:
        AuthError: The passToken is invalid or the credential exchange failed.
    """
    if not pass_token:
        raise AuthError("passToken must not be empty")
    if not user_id:
        raise AuthError("userId must not be empty")

    token.pass_token = pass_token
    token.user_id = user_id
    if device_id:
        token.device_id = device_id
    elif not token.device_id:
        token.device_id = f"an_{os.urandom(16).hex()}"

    # Set cookies (passToken + deviceId + userId)
    for name, value in {
        "passToken": pass_token,
        "deviceId": token.device_id,
        "userId": user_id,
    }.items():
        set_cookie_for_domains(http, name, value)

    logger.info("Exchanging passToken for credentials, userId={}", user_id)

    # Call serviceLogin; with the passToken cookie the server returns credentials directly
    resp = await http.get(
        XIAOMI_LOGIN_URL,
        params={"_json": "true", "sid": SERVICE_SID_HEALTH},
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    ssecurity = data.get("ssecurity", "")
    location = data.get("location", "")
    nonce_val = data.get("nonce", "")
    c_user_id = data.get("cUserId", "")

    if not ssecurity:
        raise AuthError(
            "passToken credential exchange failed: serviceLogin did not return ssecurity. "
            f"Response fields: {', '.join(sorted(data.keys()))}"
        )

    token.ssecurity = ssecurity
    token.c_user_id = c_user_id

    # Follow the location redirect to obtain serviceToken
    if location:
        sign_text = f"nonce={nonce_val}&{ssecurity}"
        sha1_digest = hashlib.sha1(sign_text.encode()).digest()
        client_sign = quote(base64.b64encode(sha1_digest).decode())
        full_url = f"{location}&clientSign={client_sign}"
        token.service_token = await extract_service_token(http, full_url)

    logger.info("passToken credential exchange complete, user_id={}", token.user_id)
