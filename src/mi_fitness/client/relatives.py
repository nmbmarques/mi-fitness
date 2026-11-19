"""Relative relationship management (add / remove / settings)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from mi_fitness.const import (
    ALL_SHARED_DATA_TYPES,
    RELATIVES_DELETE_PATH,
    RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
    RELATIVES_GET_FAMILY_MEMBER_PATH,
    RELATIVES_GET_INVITE_ID_PATH,
    RELATIVES_GET_SHARED_TYPES_PATH,
    RELATIVES_GET_TOPIC_SUBS_PATH,
    RELATIVES_LIST_PATH,
    RELATIVES_OPERATE_INVITE_PATH,
    RELATIVES_SEND_INVITE_PATH,
    RELATIVES_VERIFY_USER_PATH,
    VERIFY_TYPE_XIAOMI_ID,
)
from mi_fitness.exceptions import FamilyMemberNotFoundError
from mi_fitness.models import (
    DeleteRelativeResponse,
    FamilyMember,
    FamilyMemberResponse,
    InviteResponse,
    InviteUniqueIdResponse,
    OperateInviteResponse,
    RelativeListResponse,
    SharedDataTypesResponse,
    VerifiedUserInfo,
    VerifyUserResponse,
)

if TYPE_CHECKING:
    from mi_fitness.client.api import MiHealthClient

_DEFAULT_TOPICS = ("abnormal_event",)


def _build_auth_content(
    shared_data_types: list[str] | None,
    auth_time_range: int,
) -> dict[str, Any]:
    """Build the auth_content for relative invite requests."""
    return {
        "auth_time_range": auth_time_range,
        "auth_data": shared_data_types or ALL_SHARED_DATA_TYPES,
    }


async def get_relatives(client: MiHealthClient) -> list[FamilyMember]:
    """Get the list of relatives."""
    resp = await client._request("GET", RELATIVES_LIST_PATH)
    parsed = RelativeListResponse(**resp)
    members = parsed.relatives
    logger.info("Found {} relative(s)", len(members))
    return members


async def find_relative(client: MiHealthClient, keyword: str | int) -> FamilyMember:
    """Find a relative by nickname or UID."""
    members = await get_relatives(client)
    for m in members:
        if (isinstance(keyword, int) and m.relative_uid == keyword) or (
            isinstance(keyword, str) and keyword.lower() in m.relative_note.lower()
        ):
            return m
    raise FamilyMemberNotFoundError(f"Relative not found: {keyword}")


async def verify_user(
    client: MiHealthClient,
    verify_id: int,
    *,
    verify_type: int = VERIFY_TYPE_XIAOMI_ID,
) -> VerifiedUserInfo | None:
    """Verify user info by UID or scanned QR ID."""
    resp = await client._request(
        "GET",
        RELATIVES_VERIFY_USER_PATH,
        params={"verify_id": verify_id, "verify_type": verify_type},
    )
    parsed = VerifyUserResponse(**resp)
    return parsed.user_info


async def invite_relative(
    client: MiHealthClient,
    relative_uid: int,
    *,
    shared_data_types: list[str] | None = None,
    auth_time_range: int = 3,
    relative_note: str = "",
) -> bool:
    """Send a relative invite."""
    params: dict[str, Any] = {
        "auth_content": _build_auth_content(shared_data_types, auth_time_range),
        "relative_uid": relative_uid,
    }
    if relative_note:
        params["relative_note"] = relative_note

    resp = await client._request("POST", RELATIVES_SEND_INVITE_PATH, params=params)
    parsed = InviteResponse(**resp)
    logger.info(
        "Invite send {} (uid={})", "succeeded" if parsed.success else "failed", relative_uid
    )
    return parsed.success


async def accept_invite(
    client: MiHealthClient,
    invite_id: int,
    msg_id: int,
    *,
    shared_data_types: list[str] | None = None,
    auth_time_range: int = 3,
) -> bool:
    """Accept a relative invite."""
    return await _operate_invite(
        client,
        invite_id,
        msg_id,
        operate=1,
        shared_data_types=shared_data_types,
        auth_time_range=auth_time_range,
    )


async def reject_invite(
    client: MiHealthClient,
    invite_id: int,
    msg_id: int,
) -> bool:
    """Reject a relative invite."""
    return await _operate_invite(client, invite_id, msg_id, operate=2)


async def _operate_invite(
    client: MiHealthClient,
    invite_id: int,
    msg_id: int,
    *,
    operate: int,
    shared_data_types: list[str] | None = None,
    auth_time_range: int = 3,
) -> bool:
    """Act on a relative invite (internal)."""
    params: dict[str, Any] = {
        "auth_content": _build_auth_content(shared_data_types, auth_time_range),
        "invite_id": invite_id,
        "msg_id": msg_id,
        "operate": operate,
    }
    resp = await client._request("POST", RELATIVES_OPERATE_INVITE_PATH, params=params)
    parsed = OperateInviteResponse(**resp)
    op_name = "Accept" if operate == 1 else "Reject"
    logger.info(
        "{} invite {} (invite_id={})",
        op_name,
        "succeeded" if parsed.success else "failed",
        invite_id,
    )
    return parsed.success


async def delete_relative(client: MiHealthClient, relative_uid: int) -> bool:
    """Remove a relative relationship."""
    resp = await client._request(
        "POST",
        RELATIVES_DELETE_PATH,
        params={"relative_uid": relative_uid},
    )
    parsed = DeleteRelativeResponse(**resp)
    logger.info(
        "Remove relative {} (uid={})", "succeeded" if parsed.success else "failed", relative_uid
    )
    return parsed.success


async def get_invite_link_id(client: MiHealthClient) -> int:
    """Get the QR code invite link ID."""
    resp = await client._request("GET", RELATIVES_GET_INVITE_ID_PATH)
    parsed = InviteUniqueIdResponse(**resp)
    logger.debug("Got invite ID: {}", parsed.invite_link_id)
    return parsed.invite_link_id


async def get_shared_data_types(
    client: MiHealthClient,
    relative_uid: int,
    *,
    direction: int = 2,
) -> list[str]:
    """Get the data types a relative is sharing."""
    resp = await client._request(
        "GET",
        RELATIVES_GET_SHARED_TYPES_PATH,
        params={"relative_uid": relative_uid, "type": direction},
    )
    parsed = SharedDataTypesResponse(**resp)
    return parsed.keys


async def get_applied_shared_data_types(
    client: MiHealthClient,
    relative_uid: int,
) -> list[str]:
    """Get the shared data types that have been requested."""
    resp = await client._request(
        "GET",
        RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
        params={"relative_uid": relative_uid},
    )
    return resp.get("result", {}).get("keys", [])


async def get_family_members(client: MiHealthClient) -> list[dict[str, Any]]:
    """Get the family member list."""
    resp = await client._request("GET", RELATIVES_GET_FAMILY_MEMBER_PATH)
    parsed = FamilyMemberResponse(**resp)
    return parsed.family_user_list


async def get_topic_subscriptions(
    client: MiHealthClient,
    relative_uid: int,
    topics: list[str] | None = None,
) -> dict[str, Any]:
    """Get a relative's message subscription status."""
    topic_list = list(topics or _DEFAULT_TOPICS)
    resp = await client._request(
        "GET",
        RELATIVES_GET_TOPIC_SUBS_PATH,
        params={"relative_uid": relative_uid, "topics": topic_list},
    )
    return resp.get("result", {})
