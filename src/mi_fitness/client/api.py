"""MiHealthClient — Xiaomi Mi Fitness API client.

Thin orchestration layer: holds the HTTP client and auth state;
all business logic is delegated to the relatives / data / messages submodules.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, Self

from mi_fitness.auth import XiaomiAuth
from mi_fitness.client import data as _data
from mi_fitness.client import messages as _msg
from mi_fitness.client import relatives as _rel
from mi_fitness.client.base import create_api_http, encrypted_request
from mi_fitness.const import HEALTH_API_BASE
from mi_fitness.exceptions import TokenExpiredError
from mi_fitness.models import (
    AggregatedDataResponse,
    BloodPressureData,
    CaloriesData,
    DailySummary,
    FamilyMember,
    GoalData,
    HeartRateData,
    IntensityData,
    InviteMessage,
    LatestDataItem,
    LatestDataSnapshot,
    SleepData,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    VerifiedUserInfo,
    WeightData,
)


class MiHealthClient:
    """Xiaomi Mi Fitness API client.

    Accesses the relatives' health data API through a logged-in XiaomiAuth instance.
    All requests are RC4-encrypted and authenticated via cookies.

    Attributes:
        auth: Authentication manager.
        base_url: API base URL.
    """

    def __init__(
        self,
        auth: XiaomiAuth,
        base_url: str = HEALTH_API_BASE,
    ):
        """
        Args:
            auth: Authentication manager that has completed login.
            base_url: API base URL (defaults to the mainland China node).
        """
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http = create_api_http()
        self._refresh_lock = asyncio.Lock()

    @classmethod
    def from_token(cls, path: Path | str, **kwargs: Any) -> Self:
        """Create a client from a token file in one step.

        Args:
            path: Token file path.
            **kwargs: Extra arguments passed to MiHealthClient (e.g. base_url).

        Returns:
            A ready-to-use MiHealthClient instance.

        Raises:
            AuthError: The file does not exist or is malformed.
        """
        auth = XiaomiAuth.from_token(path)
        return cls(auth, **kwargs)

    def __repr__(self) -> str:
        uid = self.auth.token.user_id or "N/A"
        return f"MiHealthClient(user_id={uid!r}, base_url={self.base_url!r})"

    # region Internal requests
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        _allow_refresh: bool = True,
    ) -> dict[str, Any]:
        """Send an RC4-encrypted API request."""
        expired_service_token = self.auth.token.service_token
        try:
            return await encrypted_request(
                self._http,
                self.auth.token,
                method,
                path,
                self.base_url,
                params=params,
            )
        except TokenExpiredError:
            if not _allow_refresh:
                raise
            await self._refresh_auth(expired_service_token)
            return await self._request(method, path, params=params, _allow_refresh=False)

    async def _refresh_auth(self, expired_service_token: str) -> None:
        """Serialise automatic refreshes so concurrent requests don't refresh the token twice."""
        async with self._refresh_lock:
            current_service_token = self.auth.token.service_token
            if (
                expired_service_token
                and current_service_token
                and current_service_token != expired_service_token
                and self.auth.is_authenticated
            ):
                return
            await self.auth.refresh()

    # endregion

    # region Relative management
    async def get_relatives(self) -> list[FamilyMember]:
        """Get the list of relatives."""
        return await _rel.get_relatives(self)

    async def find_relative(self, keyword: str | int) -> FamilyMember:
        """Find a relative by nickname or UID."""
        return await _rel.find_relative(self, keyword)

    async def verify_user(
        self,
        verify_id: int,
        *,
        verify_type: int = 1,
    ) -> VerifiedUserInfo | None:
        """Verify user info by UID or scanned QR ID."""
        return await _rel.verify_user(self, verify_id, verify_type=verify_type)

    async def invite_relative(
        self,
        relative_uid: int,
        *,
        shared_data_types: list[str] | None = None,
        auth_time_range: int = 3,
        relative_note: str = "",
    ) -> bool:
        """Send a relative invite."""
        return await _rel.invite_relative(
            self,
            relative_uid,
            shared_data_types=shared_data_types,
            auth_time_range=auth_time_range,
            relative_note=relative_note,
        )

    async def accept_invite(
        self,
        invite_id: int,
        msg_id: int,
        *,
        shared_data_types: list[str] | None = None,
        auth_time_range: int = 3,
    ) -> bool:
        """Accept a relative invite."""
        return await _rel.accept_invite(
            self,
            invite_id,
            msg_id,
            shared_data_types=shared_data_types,
            auth_time_range=auth_time_range,
        )

    async def reject_invite(self, invite_id: int, msg_id: int) -> bool:
        """Reject a relative invite."""
        return await _rel.reject_invite(self, invite_id, msg_id)

    async def delete_relative(self, relative_uid: int) -> bool:
        """Remove a relative relationship."""
        return await _rel.delete_relative(self, relative_uid)

    async def get_invite_link_id(self) -> int:
        """Get the QR code invite link ID."""
        return await _rel.get_invite_link_id(self)

    async def get_shared_data_types(
        self,
        relative_uid: int,
        *,
        direction: int = 2,
    ) -> list[str]:
        """Get the data types a relative is sharing."""
        return await _rel.get_shared_data_types(self, relative_uid, direction=direction)

    async def get_applied_shared_data_types(self, relative_uid: int) -> list[str]:
        """Get the shared data types that have been requested."""
        return await _rel.get_applied_shared_data_types(self, relative_uid)

    async def get_family_members(self) -> list[dict[str, Any]]:
        """Get the family member list."""
        return await _rel.get_family_members(self)

    async def get_topic_subscriptions(
        self,
        relative_uid: int,
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get a relative's message subscription status."""
        return await _rel.get_topic_subscriptions(self, relative_uid, topics)

    # endregion

    # region Data queries
    async def get_latest_items(self, relative_uid: int) -> list[LatestDataItem]:
        """Get a relative's raw list of latest data items."""
        return await _data.get_latest_items(self, relative_uid)

    async def get_latest_data(self, relative_uid: int) -> LatestDataSnapshot:
        """Get a relative's latest data snapshot (strongly typed aggregate view)."""
        return await _data.get_latest_data(self, relative_uid)

    async def get_aggregated_data(
        self,
        relative_uid: int,
        key: str,
        start_time: int,
        end_time: int,
        *,
        tag: str = "daily_report",
        limit: int = 30,
    ) -> AggregatedDataResponse:
        """Get a relative's aggregated data."""
        return await _data.get_aggregated_data(
            self,
            relative_uid,
            key,
            start_time,
            end_time,
            tag=tag,
            limit=limit,
        )

    async def get_fitness_data(
        self,
        relative_uid: int,
        key: str,
        start_time: int,
        end_time: int,
        *,
        limit: int = 30,
    ) -> AggregatedDataResponse:
        """Get a relative's raw measurement/event data (e.g. weight, blood pressure, abnormal heart rate)."""
        return await _data.get_fitness_data(
            self,
            relative_uid,
            key,
            start_time,
            end_time,
            limit=limit,
        )

    async def get_heart_rate(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[HeartRateData]:
        """Get a relative's heart rate data."""
        return await _data.get_heart_rate(self, relative_uid, query_date, days=days)

    async def get_sleep(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[SleepData]:
        """Get a relative's sleep data."""
        return await _data.get_sleep(self, relative_uid, query_date, days=days)

    async def get_steps(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[StepData]:
        """Get a relative's step data."""
        return await _data.get_steps(self, relative_uid, query_date, days=days)

    async def get_weight_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[WeightData]:
        """Get a relative's weight measurements within the given window."""
        return await _data.get_weight_history(self, relative_uid, query_date, days=days)

    async def get_blood_pressure_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[BloodPressureData]:
        """Get a relative's blood pressure measurements within the given window."""
        return await _data.get_blood_pressure_history(self, relative_uid, query_date, days=days)

    async def get_weight(self, relative_uid: int) -> WeightData | None:
        """Get a relative's latest weight data."""
        return await _data.get_weight(self, relative_uid)

    async def get_calories_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[CaloriesData]:
        """Get a relative's active calorie data aggregated by day."""
        return await _data.get_calories_history(self, relative_uid, query_date, days=days)

    async def get_valid_stand_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[ValidStandData]:
        """Get a relative's valid stand count aggregated by day."""
        return await _data.get_valid_stand_history(self, relative_uid, query_date, days=days)

    async def get_intensity_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[IntensityData]:
        """Get a relative's moderate-to-vigorous activity duration aggregated by day."""
        return await _data.get_intensity_history(self, relative_uid, query_date, days=days)

    async def get_spo2_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[Spo2SummaryData]:
        """Get a relative's blood oxygen (SpO2) summary aggregated by day."""
        return await _data.get_spo2_history(self, relative_uid, query_date, days=days)

    async def get_goal(self, relative_uid: int) -> GoalData | None:
        """Get a relative's latest goal completion."""
        return await _data.get_goal(self, relative_uid)

    async def get_blood_pressure(self, relative_uid: int) -> BloodPressureData | None:
        """Get a relative's latest blood pressure data."""
        return await _data.get_blood_pressure(self, relative_uid)

    async def get_calories(self, relative_uid: int) -> CaloriesData | None:
        """Get a relative's latest active calories."""
        return await _data.get_calories(self, relative_uid)

    async def get_valid_stand(self, relative_uid: int) -> ValidStandData | None:
        """Get a relative's latest valid stand count."""
        return await _data.get_valid_stand(self, relative_uid)

    async def get_intensity(self, relative_uid: int) -> IntensityData | None:
        """Get a relative's latest moderate-to-vigorous activity duration."""
        return await _data.get_intensity(self, relative_uid)

    async def get_spo2(self, relative_uid: int) -> Spo2Data | None:
        """Get a relative's latest blood oxygen (SpO2) data."""
        return await _data.get_spo2(self, relative_uid)

    async def get_daily_summary(
        self,
        relative_uid: int,
        query_date: date | None = None,
    ) -> DailySummary:
        """Get a relative's daily combined health summary."""
        return await _data.get_daily_summary(self, relative_uid, query_date)

    async def get_latest_daily_summary(self, relative_uid: int) -> DailySummary:
        """Get a relative's daily combined health summary for the most recent day with synced data."""
        return await _data.get_latest_daily_summary(self, relative_uid)

    # endregion

    # region Messages
    async def get_invite_messages(
        self,
        *,
        limit: int = 30,
        pending_only: bool = False,
    ) -> list[InviteMessage]:
        """Get the list of relative invite messages."""
        return await _msg.get_invite_messages(self, limit=limit, pending_only=pending_only)

    async def has_new_invite(self) -> bool:
        """Check whether there are new relative invite messages."""
        return await _msg.has_new_invite(self)

    # endregion

    # region Static utilities
    @staticmethod
    def _date_to_timestamps(query_date: date | None = None) -> tuple[int, int]:
        """Convert a date into timestamps for 00:00 to 23:59:59 of that day."""
        return _data._date_to_timestamps(query_date)

    # endregion

    # region Lifecycle
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # endregion
