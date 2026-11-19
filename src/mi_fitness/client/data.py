"""Health data queries (heart rate, sleep, steps, etc.)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from mi_fitness.const import (
    DATA_KEY_BLOOD_PRESSURE,
    DATA_KEY_CALORIES,
    DATA_KEY_GOAL,
    DATA_KEY_HEART_RATE,
    DATA_KEY_INTENSITY,
    DATA_KEY_SLEEP,
    DATA_KEY_SPO2,
    DATA_KEY_STEPS,
    DATA_KEY_VALID_STAND,
    DATA_KEY_WEIGHT,
    DATA_TAG_DAILY_REPORT,
    RELATIVES_AGGREGATED_DATA_PATH,
    RELATIVES_FITNESS_DATA_PATH,
    RELATIVES_LATEST_DATA_PATH,
)
from mi_fitness.exceptions import DataNotSharedError, DataOutOfSharedTimeScopeError
from mi_fitness.models import (
    AggregatedDataItem,
    AggregatedDataResponse,
    BloodPressureData,
    CaloriesData,
    DailySummary,
    GoalData,
    HeartRateData,
    IntensityData,
    LatestDataItem,
    LatestDataResponse,
    LatestDataSnapshot,
    SleepData,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    WeightData,
)

if TYPE_CHECKING:
    from mi_fitness.client.api import MiHealthClient

_SeriesDataT = TypeVar("_SeriesDataT")
_LatestMetricT = TypeVar(
    "_LatestMetricT",
    GoalData,
    BloodPressureData,
    CaloriesData,
    IntensityData,
    Spo2Data,
    ValidStandData,
    WeightData,
)


async def _get_first_shared_or_none(
    fetcher: Callable[[], Awaitable[list[_SeriesDataT]]],
) -> _SeriesDataT | None:
    """For summary endpoints only: return None if not shared; re-raise any other exception."""
    try:
        result = await fetcher()
    except DataOutOfSharedTimeScopeError:
        raise
    except DataNotSharedError:
        return None
    return result[0] if result else None


# region Latest data
async def _get_latest_response(client: MiHealthClient, relative_uid: int) -> LatestDataResponse:
    """Fetch and parse the latest data response."""
    resp = await client._request(
        "GET",
        RELATIVES_LATEST_DATA_PATH,
        params={"relative_uid": relative_uid},
    )
    return LatestDataResponse(**resp)


async def get_latest_items(client: MiHealthClient, relative_uid: int) -> list[LatestDataItem]:
    """Get a relative's raw list of latest data items."""
    return (await _get_latest_response(client, relative_uid)).data_items


async def get_latest_data(client: MiHealthClient, relative_uid: int) -> LatestDataSnapshot:
    """Get a relative's latest data snapshot (strongly typed aggregate view)."""
    return (await _get_latest_response(client, relative_uid)).snapshot


async def _get_latest_metric(
    client: MiHealthClient,
    relative_uid: int,
    *,
    attr_name: str,
    shared_key: str,
) -> _LatestMetricT | None:
    """Read a single item from the latest snapshot, raising a clear exception if it is not shared."""
    latest = await get_latest_data(client, relative_uid)
    value = getattr(latest, attr_name)
    if value is not None:
        return value

    shared_types = await client.get_shared_data_types(relative_uid)
    if shared_key not in shared_types:
        raise DataNotSharedError(f"Data type not shared: {shared_key}", data_type=shared_key)
    return None


# endregion


# region Aggregated data
async def get_aggregated_data(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    start_time: int,
    end_time: int,
    *,
    tag: str = DATA_TAG_DAILY_REPORT,
    limit: int = 30,
) -> AggregatedDataResponse:
    """Get a relative's aggregated data."""
    resp = await client._request(
        "GET",
        RELATIVES_AGGREGATED_DATA_PATH,
        params={
            "relative_uid": relative_uid,
            "key": key,
            "tag": tag,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
        },
    )
    return AggregatedDataResponse(**resp)


async def get_fitness_data(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    start_time: int,
    end_time: int,
    *,
    limit: int = 30,
) -> AggregatedDataResponse:
    """Get a relative's raw measurement/event data (e.g. weight, blood pressure, abnormal heart rate)."""
    resp = await client._request(
        "GET",
        RELATIVES_FITNESS_DATA_PATH,
        params={
            "relative_uid": relative_uid,
            "key": key,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
        },
    )
    return AggregatedDataResponse(**resp)


# endregion


# region Convenience methods
def _date_to_timestamps(query_date: date | None = None) -> tuple[int, int]:
    """Convert a date into timestamps for 00:00 to 23:59:59 of that day."""
    d = query_date or date.today()
    tz = timezone(timedelta(hours=8))
    start = int(datetime(d.year, d.month, d.day, tzinfo=tz).timestamp())
    end = start + 86400 - 1
    return start, end


def _build_window_timestamps(query_date: date | None, days: int) -> tuple[int, int, int]:
    """Build a query window that ends on ``query_date``."""
    window_days = max(days, 1)
    _, end = _date_to_timestamps(query_date)
    start = end - 86400 * window_days + 1
    return start, end, window_days


def _parse_series_items(
    items: list[AggregatedDataItem],
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
) -> list[_SeriesDataT]:
    """Parse data items one by one, skipping individual malformed entries."""
    series: list[_SeriesDataT] = []
    for item in items:
        try:
            series.append(parser(item))
        except ValidationError:
            continue
    return series


async def _get_aggregated_series(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[_SeriesDataT]:
    """Fetch aggregated data for a date range and convert it to the target model.

    ``query_date`` is the last day of the window; ``days=7`` fetches that day and the 6 days before it.
    """
    start, end, window_days = _build_window_timestamps(query_date, days)
    resp = await get_aggregated_data(client, relative_uid, key, start, end, limit=window_days)
    return _parse_series_items(resp.data_items, parser)


async def _get_fitness_series(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[_SeriesDataT]:
    """Fetch raw measurement records for a time window.

    ``get_fitness_data`` is not a one-record-per-day aggregate endpoint, so a looser fixed ``limit=30`` is used,
    to avoid truncating results when there are several measurements in a week.
    """
    start, end, window_days = _build_window_timestamps(query_date, days)
    resp = await get_fitness_data(
        client,
        relative_uid,
        key,
        start,
        end,
        limit=max(window_days, 30),
    )
    return _parse_series_items(resp.data_items, parser)


async def get_heart_rate(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[HeartRateData]:
    """Get a relative's heart rate data."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_HEART_RATE,
        AggregatedDataItem.as_heart_rate,
        query_date,
        days=days,
    )


async def get_sleep(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[SleepData]:
    """Get a relative's sleep data."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_SLEEP,
        AggregatedDataItem.as_sleep,
        query_date,
        days=days,
    )


async def get_steps(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[StepData]:
    """Get a relative's step data."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_STEPS,
        AggregatedDataItem.as_steps,
        query_date,
        days=days,
    )


async def get_calories_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[CaloriesData]:
    """Get a relative's active calorie data aggregated by day."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_CALORIES,
        AggregatedDataItem.as_calories,
        query_date,
        days=days,
    )


async def get_valid_stand_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[ValidStandData]:
    """Get a relative's valid stand count aggregated by day."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_VALID_STAND,
        AggregatedDataItem.as_valid_stand,
        query_date,
        days=days,
    )


async def get_intensity_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[IntensityData]:
    """Get a relative's moderate-to-vigorous activity duration aggregated by day."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_INTENSITY,
        AggregatedDataItem.as_intensity,
        query_date,
        days=days,
    )


async def get_spo2_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[Spo2SummaryData]:
    """Get a relative's blood oxygen (SpO2) summary aggregated by day."""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_SPO2,
        AggregatedDataItem.as_spo2,
        query_date,
        days=days,
    )


async def get_weight_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[WeightData]:
    """Get a relative's weight measurements within the given window."""
    return await _get_fitness_series(
        client,
        relative_uid,
        DATA_KEY_WEIGHT,
        AggregatedDataItem.as_weight,
        query_date,
        days=days,
    )


async def get_blood_pressure_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[BloodPressureData]:
    """Get a relative's blood pressure measurements within the given window."""
    return await _get_fitness_series(
        client,
        relative_uid,
        DATA_KEY_BLOOD_PRESSURE,
        AggregatedDataItem.as_blood_pressure,
        query_date,
        days=days,
    )


async def get_weight(client: MiHealthClient, relative_uid: int) -> WeightData | None:
    """Get a relative's latest weight data."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="weight",
        shared_key=DATA_KEY_WEIGHT,
    )


async def get_goal(client: MiHealthClient, relative_uid: int) -> GoalData | None:
    """Get a relative's latest goal completion."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="goal",
        shared_key=DATA_KEY_GOAL,
    )


async def get_blood_pressure(client: MiHealthClient, relative_uid: int) -> BloodPressureData | None:
    """Get a relative's latest blood pressure data."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="blood_pressure",
        shared_key=DATA_KEY_BLOOD_PRESSURE,
    )


async def get_calories(client: MiHealthClient, relative_uid: int) -> CaloriesData | None:
    """Get a relative's latest active calories."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="calories",
        shared_key=DATA_KEY_CALORIES,
    )


async def get_valid_stand(client: MiHealthClient, relative_uid: int) -> ValidStandData | None:
    """Get a relative's latest valid stand count."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="valid_stand",
        shared_key=DATA_KEY_VALID_STAND,
    )


async def get_intensity(client: MiHealthClient, relative_uid: int) -> IntensityData | None:
    """Get a relative's latest moderate-to-vigorous activity duration."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="intensity",
        shared_key=DATA_KEY_INTENSITY,
    )


async def get_spo2(client: MiHealthClient, relative_uid: int) -> Spo2Data | None:
    """Get a relative's latest blood oxygen (SpO2) data."""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="spo2",
        shared_key=DATA_KEY_SPO2,
    )


async def get_daily_summary(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
) -> DailySummary:
    """Get a relative's daily combined health summary (heart rate, sleep and steps requested concurrently)."""
    d = query_date or date.today()

    heart_rate, sleep, steps = await asyncio.gather(
        _get_first_shared_or_none(lambda: get_heart_rate(client, relative_uid, d)),
        _get_first_shared_or_none(lambda: get_sleep(client, relative_uid, d)),
        _get_first_shared_or_none(lambda: get_steps(client, relative_uid, d)),
    )

    return DailySummary(
        date=d.isoformat(),
        relative_uid=relative_uid,
        heart_rate=heart_rate,
        sleep=sleep,
        steps=steps,
    )


async def get_latest_daily_summary(
    client: MiHealthClient,
    relative_uid: int,
) -> DailySummary:
    """Get a relative's daily combined health summary for the most recent day with synced data."""
    member = await client.find_relative(relative_uid)
    query_date = date.today()
    if member.latest_data_time > 0:
        query_date = datetime.fromtimestamp(member.latest_data_time, tz=UTC).date()
    else:
        latest = await get_latest_data(client, relative_uid)
        if latest.updated_time > 0:
            query_date = datetime.fromtimestamp(latest.updated_time, tz=UTC).date()
    return await get_daily_summary(client, relative_uid, query_date)


# endregion
