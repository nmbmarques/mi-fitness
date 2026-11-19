"""STS security token exchange."""

from __future__ import annotations

import time

from loguru import logger

from mi_fitness.const import STS_HEALTH_URL
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken


async def sts_exchange(http: RetryAsyncClient, token: AuthToken) -> None:
    """STS security token exchange.

    Completes STS verification using the deviceId. This step is non-fatal; a failure only logs a warning.

    Args:
        http: HTTP client.
        token: AuthToken that already has a device_id.
    """
    params = {
        "d": token.device_id,
        "ticket": "0",
        "pwd": "0",
        "p_ts": str(int(time.time() * 1000)),
        "fid": "0",
        "p_lm": "2",
        "p_ur": "CN",
    }

    try:
        resp = await http.get(STS_HEALTH_URL, params=params)
        if resp.text.strip() == "ok":
            logger.debug("STS exchange succeeded")
        else:
            logger.warning("STS exchange response: {}", resp.text[:100])
    except Exception as e:
        logger.warning("STS exchange failed (non-fatal): {}", e)
