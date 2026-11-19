"""Message (invite notification) queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from mi_fitness.const import (
    MESSAGE_CHECK_NEW_PATH,
    MESSAGE_GET_LIST_PATH,
    MESSAGE_MODULE_RELATIVES,
)
from mi_fitness.models import CheckNewMsgResponse, InviteMessage, MessageListResponse

if TYPE_CHECKING:
    from mi_fitness.client.api import MiHealthClient


async def get_invite_messages(
    client: MiHealthClient,
    *,
    limit: int = 30,
    pending_only: bool = False,
) -> list[InviteMessage]:
    """Get the list of relative invite messages."""
    resp = await client._request(
        "POST",
        MESSAGE_GET_LIST_PATH,
        params={"module": MESSAGE_MODULE_RELATIVES, "limit": limit},
    )
    parsed = MessageListResponse(**resp)
    messages = parsed.messages
    if pending_only:
        messages = [m for m in messages if m.is_pending]
    logger.debug(
        "Fetched invite messages: {} (pending: {})",
        len(parsed.messages),
        sum(1 for m in parsed.messages if m.is_pending),
    )
    return messages


async def has_new_invite(client: MiHealthClient) -> bool:
    """Check whether there are new relative invite messages."""
    resp = await client._request(
        "POST",
        MESSAGE_CHECK_NEW_PATH,
        params={"module": [MESSAGE_MODULE_RELATIVES], "begin_time": 0},
    )
    parsed = CheckNewMsgResponse(**resp)
    return parsed.has_new(MESSAGE_MODULE_RELATIVES)
