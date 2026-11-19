"""Health data structures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import IntEnum
from functools import cached_property
from typing import Any, TypeVar

from pydantic import AliasChoices, BaseModel, Field, ValidationError, field_validator

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _ts_to_datetime(ts: int) -> datetime | None:
    """Convert a timestamp in seconds to a UTC datetime; 0 returns None."""
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def _coerce_bool(value: Any) -> bool:
    """Normalise a bool / int / str returned by the API to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort conversion of an API value to an integer."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional_int(value: Any) -> int | None:
    """Best-effort conversion of an API value to an integer; returns None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_dict(value: Any) -> dict[str, Any]:
    """Keep only dict results; treat anything else as an empty object."""
    return value if isinstance(value, dict) else {}


def _coerce_dict_list(value: Any) -> list[dict[str, Any]]:
    """Safely normalise dict entries from a single object or a list."""
    if isinstance(value, dict):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        return []
    return [item for item in candidates if isinstance(item, dict) and item]


def _coerce_str_list(value: Any) -> list[str]:
    """Keep only a list of non-empty strings."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _parse_model_list(value: Any, model: type[_ModelT]) -> list[_ModelT]:
    """Safely parse a list of models, skipping obviously broken entries."""
    parsed: list[_ModelT] = []
    for item in _coerce_dict_list(value):
        try:
            parsed.append(model.model_validate(item))
        except ValidationError:
            continue
    return parsed


def _parse_model(value: Any, model: type[_ModelT]) -> _ModelT | None:
    """Safely parse a single model; returns None on failure."""
    try:
        return model.model_validate(value)
    except ValidationError:
        return None


class _DictResultResponse(BaseModel):
    """Base class for responses whose result should be a dict."""

    code: int = 0
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: Any) -> dict[str, Any]:
        return _coerce_dict(value)


class _ListResultResponse(BaseModel):
    """Base class for responses whose result should be a list."""

    code: int = 0
    message: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_dict_list(value)


# region Token persistence
class AuthToken(BaseModel):
    """Login credentials, serialisable for persistent storage.

    Attributes:
        user_id: Xiaomi user ID (userId).
        c_user_id: cUserId (used for cookie authentication).
        service_token: serviceToken (used for cookie authentication).
        ssecurity: Encryption key (used for RC4 encryption/decryption).
        pass_token: passToken (can be used for STS exchange).
        device_id: Device identifier.
    """

    user_id: str = ""
    c_user_id: str = ""
    service_token: str = ""
    ssecurity: str = ""
    pass_token: str = ""
    device_id: str = ""


# endregion


# region Relatives
class FamilyMember(BaseModel):
    """Relative info (from the get_relative_list response).

    Attributes:
        relative_uid: The relative's Xiaomi user UID (integer).
        relative_note: Nickname / note.
        relative_icon: Avatar URL.
        latest_data_time: Timestamp of the latest data.
        latest_abnormal_record_time: Timestamp of the latest abnormal record.
        source_tag: Source tag.
    """

    relative_uid: int
    relative_note: str = ""
    relative_icon: str = ""
    latest_data_time: int = 0
    latest_abnormal_record_time: int | None = 0
    source_tag: int = 0

    def __str__(self) -> str:
        return f"{self.relative_note or 'Unnamed'} (UID: {self.relative_uid})"


# endregion


# region Latest heart rate
class LatestHeartRate(BaseModel):
    """Real-time heart rate point (from heart rate aggregated data or the latest_hr field of get_latest_data).

    Attributes:
        bpm: Heart rate (beats per minute).
        time: Sample timestamp.
    """

    bpm: int = 0
    time: int = 0


# endregion


# region Heart rate
class HeartRateData(BaseModel):
    """Daily heart rate summary (from get_aggregated_data key=heart_rate).

    Attributes:
        time: Data timestamp (midnight of the day).
        avg_hr: Daily average heart rate.
        avg_rhr: Daily average resting heart rate.
        max_hr: Maximum heart rate.
        min_hr: Minimum heart rate.
        latest_hr: Most recent heart rate sample.
        abnormal_hr_count: Number of abnormal heart rate events.
        aerobic_hr_zone_duration: Time in the aerobic heart rate zone (minutes).
        anaerobic_hr_zone_duration: Time in the anaerobic heart rate zone (minutes).
        extreme_hr_zone_duration: Time in the extreme (max) heart rate zone (minutes).
        fat_burning_hr_zone_duration: Time in the fat-burning heart rate zone (minutes).
        warm_up_hr_zone_duration: Time in the warm-up heart rate zone (minutes).
    """

    time: int = 0
    avg_hr: int = 0
    avg_rhr: int = 0
    max_hr: int = 0
    min_hr: int = 0
    latest_hr: LatestHeartRate | None = None
    abnormal_hr_count: int = 0
    aerobic_hr_zone_duration: int = 0
    anaerobic_hr_zone_duration: int = 0
    extreme_hr_zone_duration: int = 0
    fat_burning_hr_zone_duration: int = 0
    warm_up_hr_zone_duration: int = 0

    def __str__(self) -> str:
        return (
            f"HeartRate(avg={self.avg_hr}bpm, resting={self.avg_rhr}, "
            f"range={self.min_hr}-{self.max_hr})"
        )

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region Sleep segments
class SleepSegment(BaseModel):
    """Sleep segment (from segment_details in the sleep value).

    Attributes:
        bedtime: Time fell asleep (timestamp).
        wake_up_time: Wake-up time (timestamp).
        duration: Duration (minutes).
        sleep_deep_duration: Deep sleep duration (minutes).
        sleep_light_duration: Light sleep duration (minutes).
        timezone: Timezone offset.
        awake_count: Number of awakenings.
        sleep_awake_duration: Awake duration (minutes).
    """

    bedtime: int = 0
    wake_up_time: int = 0
    duration: int = 0
    sleep_deep_duration: int = 0
    sleep_light_duration: int = 0
    timezone: int = 0
    awake_count: int = 0
    sleep_awake_duration: int = 0


# endregion


# region Sleep
class SleepData(BaseModel):
    """Daily sleep summary (from get_aggregated_data key=sleep).

    Attributes:
        time: Data timestamp.
        total_duration: Total sleep duration (minutes).
        sleep_score: Sleep score (0-100).
        sleep_stage: Number of sleep stages.
        sleep_deep_duration: Deep sleep duration (minutes).
        sleep_light_duration: Light sleep duration (minutes).
        sleep_rem_duration: REM duration (minutes).
        sleep_awake_duration: Awake duration (minutes).
        long_sleep_evaluation: Long-term (night) sleep evaluation.
        day_sleep_evaluation: Daytime nap evaluation.
        avg_hr: Average heart rate during sleep.
        max_hr: Maximum heart rate during sleep.
        min_hr: Minimum heart rate during sleep.
        avg_spo2: Average blood oxygen during sleep.
        segment_details: List of sleep segments.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    total_duration: int = 0
    sleep_score: int = 0
    sleep_stage: int = 0
    sleep_deep_duration: int = 0
    sleep_light_duration: int = 0
    sleep_rem_duration: int = 0
    sleep_awake_duration: int = 0
    long_sleep_evaluation: int = 0
    day_sleep_evaluation: int = 0
    avg_hr: int = 0
    max_hr: int = 0
    min_hr: int = 0
    avg_spo2: int = 0
    segment_details: list[SleepSegment] = Field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Sleep({self.total_duration}min, score={self.sleep_score}/100, "
            f"deep={self.sleep_deep_duration}min, light={self.sleep_light_duration}min, "
            f"rem={self.sleep_rem_duration}min)"
        )

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region Steps
class StepData(BaseModel):
    """Daily step summary (from get_aggregated_data key=steps).

    Attributes:
        time: Data timestamp.
        steps: Step count.
        distance: Distance (metres).
        calories: Calories burned.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    steps: int = 0
    distance: int = 0
    calories: int = 0
    goal: int = 0

    def __str__(self) -> str:
        return f"Steps({self.steps} steps, {self.distance}m, {self.calories}cal)"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region Weight
class WeightData(BaseModel):
    """Weight data (from get_latest_data / get_fitness_data key=weight).

    Attributes:
        time: Data timestamp.
        weight: Weight (kg).
        bmi: BMI.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    weight: float = 0.0
    bmi: float = 0.0

    def __str__(self) -> str:
        return f"Weight({self.weight}kg, BMI={self.bmi})"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region Blood pressure
class BloodPressureData(BaseModel):
    """Blood pressure data (from get_latest_data / get_fitness_data key=blood_pressure).

    Attributes:
        time: Data timestamp.
        systolic: Systolic pressure (upper, mmHg).
        diastolic: Diastolic pressure (lower, mmHg).
        pulse: Pulse (bpm).
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    systolic: int = Field(default=0, validation_alias=AliasChoices("systolic", "systolic_pressure"))
    diastolic: int = Field(
        default=0, validation_alias=AliasChoices("diastolic", "diastolic_pressure")
    )
    pulse: int | None = None

    def __str__(self) -> str:
        base = f"BloodPressure({self.systolic}/{self.diastolic} mmHg)"
        return f"{base}, pulse={self.pulse}" if self.pulse is not None else base

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region Latest snapshot metrics
class GoalMetric(IntEnum):
    """A single goal type within the activity metrics."""

    STEPS = 1
    CALORIES = 2
    INTENSITY = 4

    @classmethod
    def from_field(cls, field: int) -> GoalMetric | None:
        """Map the field number returned by the API to a known goal type."""
        try:
            return cls(field)
        except ValueError:
            return None

    @property
    def key(self) -> str:
        """Stable English key, suitable for code branches and serialisation."""
        return {
            GoalMetric.STEPS: "steps",
            GoalMetric.CALORIES: "calories",
            GoalMetric.INTENSITY: "intensity",
        }[self]

    @property
    def label(self) -> str:
        """Display name close to the app's wording."""
        return {
            GoalMetric.STEPS: "Steps",
            GoalMetric.CALORIES: "Calories",
            GoalMetric.INTENSITY: "Moderate-to-vigorous activity",
        }[self]


class GoalItem(BaseModel):
    """A single health goal entry.

    Attributes:
        field: Goal type number.
        target_value: Target value.
        achieved_value: Achieved value.
    """

    field: int = 0
    target_value: int | float = 0
    achieved_value: int | float = 0

    @property
    def metric(self) -> GoalMetric | None:
        """Known goal type; returns None for an unknown field."""
        return GoalMetric.from_field(self.field)

    @property
    def metric_key(self) -> str:
        """Goal key; unknown types keep the field number to help debugging."""
        metric = self.metric
        return metric.key if metric is not None else f"unknown:{self.field}"

    @property
    def metric_label(self) -> str:
        """Goal display name; unknown types keep the raw number."""
        metric = self.metric
        return metric.label if metric is not None else f"Unknown goal ({self.field})"


class GoalData(BaseModel):
    """Daily goal completion (from get_latest_data key=goal).

    Attributes:
        time: Timestamp of the day the goals belong to.
        goal_items: All goal items for the day.

    Convenience properties:
        ``steps_goal`` / ``calories_goal`` / ``intensity_goal`` return the corresponding goal entry.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    goal_items: list[GoalItem] = Field(default_factory=list)

    @field_validator("goal_items", mode="before")
    @classmethod
    def _normalize_goal_items(cls, value: Any) -> list[GoalItem]:
        return _parse_model_list(value, GoalItem)

    def __str__(self) -> str:
        return f"GoalData({len(self.goal_items)} items)"

    @cached_property
    def items_by_field(self) -> dict[int, GoalItem]:
        """Index goal items by their raw field number."""
        return {item.field: item for item in self.goal_items}

    @property
    def available_metrics(self) -> list[GoalMetric]:
        """Known goal types present in the current response."""
        metrics: list[GoalMetric] = []
        for item in self.goal_items:
            if item.metric is not None:
                metrics.append(item.metric)
        return metrics

    @property
    def unknown_goal_items(self) -> list[GoalItem]:
        """Goal items in the current response that were not recognised."""
        return [item for item in self.goal_items if item.metric is None]

    def get_item(self, metric: GoalMetric | int) -> GoalItem | None:
        """Read the entry for the given goal type."""
        return self.items_by_field.get(int(metric))

    @property
    def steps_goal(self) -> GoalItem | None:
        """Steps goal."""
        return self.get_item(GoalMetric.STEPS)

    @property
    def calories_goal(self) -> GoalItem | None:
        """Calories goal."""
        return self.get_item(GoalMetric.CALORIES)

    @property
    def intensity_goal(self) -> GoalItem | None:
        """Moderate-to-vigorous activity goal."""
        return self.get_item(GoalMetric.INTENSITY)

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


class CaloriesData(BaseModel):
    """Daily active calories (from get_latest_data key=calories).

    Attributes:
        time: Data timestamp.
        calories: Active calories burned.
        goal: Calorie goal.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    calories: int = 0
    goal: int = 0

    def __str__(self) -> str:
        return f"Calories({self.calories} cal, goal={self.goal})"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


class ValidStandData(BaseModel):
    """Daily valid stand count (from get_latest_data key=valid_stand).

    Attributes:
        time: Data timestamp.
        count: Number of valid stands.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    count: int = 0

    def __str__(self) -> str:
        return f"ValidStand({self.count})"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


class IntensityData(BaseModel):
    """Daily moderate-to-vigorous activity duration (from get_latest_data key=intensity).

    Attributes:
        time: Data timestamp.
        duration: Moderate-to-vigorous activity duration (minutes).
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    duration: int = 0

    def __str__(self) -> str:
        return f"Intensity({self.duration} min)"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


class Spo2Data(BaseModel):
    """Latest blood oxygen data (from get_latest_data key=spo2).

    Attributes:
        time: Measurement timestamp.
        spo2: Blood oxygen percentage.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    spo2: int = 0

    def __str__(self) -> str:
        return f"Spo2({self.spo2}%)"

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


class Spo2SummaryData(BaseModel):
    """Daily blood oxygen summary (from get_aggregated_data key=spo2).

    Attributes:
        time: Data timestamp.
        avg_spo2: Average blood oxygen.
        max_spo2: Highest blood oxygen.
        min_spo2: Lowest blood oxygen.
        lack_spo2_count: Number of low blood oxygen events.
        latest_spo2: Most recent blood oxygen sample of the day.
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    avg_spo2: int = 0
    max_spo2: int = 0
    min_spo2: int = 0
    lack_spo2_count: int = 0
    latest_spo2: Spo2Data | None = None

    def __str__(self) -> str:
        return (
            f"Spo2Summary(avg={self.avg_spo2}%, range={self.min_spo2}-{self.max_spo2}, "
            f"lack={self.lack_spo2_count})"
        )

    @property
    def at(self) -> datetime | None:
        """Data time (UTC datetime)."""
        return _ts_to_datetime(self.time)


# endregion


# region User verification
class VerifiedUserInfo(BaseModel):
    """User info from the verify_userinfo_by_id response.

    Attributes:
        user_id: Xiaomi user UID.
        nickname: Nickname.
        icon: Avatar URL.
    """

    user_id: int = Field(alias="userId", default=0)
    nickname: str = ""
    icon: str = ""

    model_config = {"populate_by_name": True}


# endregion


# region Latest data item
class LatestDataItem(BaseModel):
    """A single data item from the get_latest_data response.

    The value field is a JSON string that must be parsed into the matching type based on key.

    Attributes:
        time: Data timestamp.
        key: Data type (heart_rate / sleep / steps / weight / blood_pressure, etc.).
        value: JSON string or number.
    """

    time: int = 0
    key: str = ""
    value: str | int | float = ""

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, value: Any) -> str | int | float:
        """Make sure dict/list values can be parsed the same way."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (str, int, float)):
            return value
        return ""

    def parse_value(self) -> dict[str, Any] | int | float:
        """Parse the value field from a JSON string into a dict.

        Returns:
            The parsed dict or the raw number.
        """
        if isinstance(self.value, (int, float)):
            return self.value
        try:
            parsed = json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return {}
        if isinstance(parsed, (dict, int, float)):
            return parsed
        return {}

    def _parse_dict_value(self) -> dict[str, Any]:
        """Parse value into a dict; returns an empty object on failure."""
        parsed = self.parse_value()
        return parsed if isinstance(parsed, dict) else {}

    def as_goal(self) -> GoalData | None:
        """Parse as goal completion data."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, GoalData)

    def as_heart_rate(self) -> LatestHeartRate | None:
        """Parse as the latest heart rate sample."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, LatestHeartRate)

    def as_sleep(self) -> SleepData | None:
        """Parse as the latest sleep summary."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        segments = data.pop("segment_details", [])
        data["segment_details"] = _parse_model_list(segments, SleepSegment)
        return _parse_model(data, SleepData)

    def as_steps(self) -> StepData | None:
        """Parse as the latest step summary."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, StepData)

    def as_weight(self) -> WeightData | None:
        """Parse as the latest weight."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, WeightData)

    def as_blood_pressure(self) -> BloodPressureData | None:
        """Parse as the latest blood pressure."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, BloodPressureData)

    def as_calories(self) -> CaloriesData | None:
        """Parse as the latest calorie summary."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, CaloriesData)

    def as_valid_stand(self) -> ValidStandData | None:
        """Parse as the latest valid stand stats."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, ValidStandData)

    def as_intensity(self) -> IntensityData | None:
        """Parse as the latest moderate-to-vigorous activity duration."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, IntensityData)

    def as_spo2(self) -> Spo2Data | None:
        """Parse as the latest blood oxygen."""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, Spo2Data)


# endregion


# region Aggregated data item
class AggregatedDataItem(BaseModel):
    """A single data item from the get_aggregated_data response.

    Attributes:
        sid: Data source SID.
        tag: Data tag (e.g. daily_report).
        key: Data type.
        time: Data timestamp.
        value: JSON string value.
        update_time: Update timestamp.
        watermark: Watermark (used for incremental sync).
        source_sid_list: List of data sources.
    """

    sid: str = ""
    tag: str = ""
    key: str = ""
    time: int = 0
    value: str = ""
    update_time: int = 0
    watermark: str = ""
    source_sid_list: list[str] = Field(default_factory=list)

    @field_validator("watermark", mode="before")
    @classmethod
    def _stringify_watermark(cls, v: Any) -> str:
        """The API sometimes returns watermark as an int."""
        return str(v) if v is not None else ""

    @field_validator("value", mode="before")
    @classmethod
    def _stringify_value(cls, v: Any) -> str:
        """Make sure value is always a string (the API may return a dict)."""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v) if v is not None else ""

    def parse_value(self) -> dict[str, Any]:
        """Parse the value field from a JSON string into a dict."""
        try:
            parsed = json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def as_heart_rate(self) -> HeartRateData:
        """Parse as heart rate data."""
        data = self.parse_value()
        data["time"] = self.time
        latest = data.get("latest_hr")
        if isinstance(latest, dict):
            data["latest_hr"] = LatestHeartRate.model_validate(latest)
        elif latest is not None:
            data["latest_hr"] = None
        return HeartRateData.model_validate(data)

    def as_sleep(self) -> SleepData:
        """Parse as sleep data."""
        data = self.parse_value()
        data["time"] = self.time
        segments = data.pop("segment_details", [])
        data["segment_details"] = _parse_model_list(segments, SleepSegment)
        return SleepData.model_validate(data)

    def as_steps(self) -> StepData:
        """Parse as step data."""
        data = self.parse_value()
        data["time"] = self.time
        return StepData.model_validate(data)

    def as_weight(self) -> WeightData:
        """Parse as weight history data."""
        data = self.parse_value()
        data["time"] = self.time
        return WeightData.model_validate(data)

    def as_blood_pressure(self) -> BloodPressureData:
        """Parse as blood pressure history data."""
        data = self.parse_value()
        data["time"] = self.time
        return BloodPressureData.model_validate(data)

    def as_calories(self) -> CaloriesData:
        """Parse as calorie data."""
        data = self.parse_value()
        data["time"] = self.time
        return CaloriesData.model_validate(data)

    def as_valid_stand(self) -> ValidStandData:
        """Parse as valid stand data."""
        data = self.parse_value()
        data["time"] = self.time
        return ValidStandData.model_validate(data)

    def as_intensity(self) -> IntensityData:
        """Parse as moderate-to-vigorous activity duration data."""
        data = self.parse_value()
        data["time"] = self.time
        return IntensityData.model_validate(data)

    def as_spo2(self) -> Spo2SummaryData:
        """Parse as blood oxygen summary data."""
        data = self.parse_value()
        data["time"] = self.time
        latest = data.get("latest_spo2")
        if isinstance(latest, dict):
            data["latest_spo2"] = _parse_model(latest, Spo2Data)
        elif latest is not None:
            data["latest_spo2"] = None
        return Spo2SummaryData.model_validate(data)


# endregion


# region Daily summary
class DailySummary(BaseModel):
    """Daily health data summary (returned by get_daily_summary).

    Attributes:
        date: Query date (ISO format).
        relative_uid: Relative's UID.
        heart_rate: Heart rate summary data.
        sleep: Sleep summary data.
        steps: Step summary data.
    """

    date: str = ""
    relative_uid: int = 0
    heart_rate: HeartRateData | None = None
    sleep: SleepData | None = None
    steps: StepData | None = None

    def __str__(self) -> str:
        parts = [f"DailySummary({self.date}, UID={self.relative_uid}"]
        if self.heart_rate:
            parts.append(f"hr={self.heart_rate.avg_hr}bpm")
        if self.sleep:
            parts.append(f"sleep={self.sleep.total_duration}min")
        if self.steps:
            parts.append(f"steps={self.steps.steps}")
        return ", ".join(parts) + ")"


# endregion


# region Latest snapshot
class LatestDataSnapshot(BaseModel):
    """Latest health snapshot.

    Collapses the heterogeneous data_list of get_latest_data into fixed fields; payloads with unknown keys or that fail to parse
    are kept in extras, so a single malformed entry doesn't make the caller lose the whole snapshot.
    """

    updated_time: int = 0
    goal: GoalData | None = None
    heart_rate: LatestHeartRate | None = None
    sleep: SleepData | None = None
    blood_pressure: BloodPressureData | None = None
    steps: StepData | None = None
    calories: CaloriesData | None = None
    valid_stand: ValidStandData | None = None
    intensity: IntensityData | None = None
    weight: WeightData | None = None
    spo2: Spo2Data | None = None
    extras: dict[str, dict[str, Any] | int | float] = Field(default_factory=dict)

    @classmethod
    def from_items(
        cls,
        items: list[LatestDataItem],
        *,
        updated_time: int = 0,
    ) -> LatestDataSnapshot:
        """Build a typed snapshot from the raw data_list."""
        payload: dict[str, Any] = {"updated_time": updated_time}
        extras: dict[str, dict[str, Any] | int | float] = {}
        parsers = {
            "goal": LatestDataItem.as_goal,
            "heart_rate": LatestDataItem.as_heart_rate,
            "sleep": LatestDataItem.as_sleep,
            "blood_pressure": LatestDataItem.as_blood_pressure,
            "steps": LatestDataItem.as_steps,
            "calories": LatestDataItem.as_calories,
            "valid_stand": LatestDataItem.as_valid_stand,
            "intensity": LatestDataItem.as_intensity,
            "weight": LatestDataItem.as_weight,
            "spo2": LatestDataItem.as_spo2,
        }

        for item in items:
            parser = parsers.get(item.key)
            raw_value = item.parse_value()
            if parser is None:
                extras[item.key] = raw_value
                continue

            parsed = parser(item)
            if parsed is not None:
                payload[item.key] = parsed
                continue

            if raw_value not in ({}, "", 0, 0.0):
                extras[item.key] = raw_value

        return cls(**payload, extras=extras)

    def __str__(self) -> str:
        keys = ", ".join(self.available_keys) or "empty"
        return f"LatestDataSnapshot({keys})"

    @property
    def at(self) -> datetime | None:
        """Snapshot update time (UTC datetime)."""
        return _ts_to_datetime(self.updated_time)

    @property
    def available_keys(self) -> list[str]:
        """Data keys available in the current snapshot."""
        known_keys = [
            "goal",
            "heart_rate",
            "sleep",
            "blood_pressure",
            "steps",
            "calories",
            "valid_stand",
            "intensity",
            "weight",
            "spo2",
        ]
        keys = [key for key in known_keys if getattr(self, key) is not None]
        keys.extend(sorted(self.extras))
        return keys


# endregion


# region API response wrappers
class RelativeListResponse(_DictResultResponse):
    """get_relative_list response."""

    @property
    def relatives(self) -> list[FamilyMember]:
        """Parse the list of relatives."""
        return _parse_model_list(self.result.get("relative_list"), FamilyMember)


class LatestDataResponse(_DictResultResponse):
    """get_latest_data response."""

    @property
    def data_items(self) -> list[LatestDataItem]:
        """Parse the list of data items."""
        return _parse_model_list(self.result.get("data_list"), LatestDataItem)

    @property
    def latest_data_time(self) -> int:
        """Latest data update time."""
        return _coerce_int(self.result.get("latest_data_time"), default=0)

    @property
    def snapshot(self) -> LatestDataSnapshot:
        """Parse into a typed snapshot."""
        return LatestDataSnapshot.from_items(self.data_items, updated_time=self.latest_data_time)


class AggregatedDataResponse(_DictResultResponse):
    """get_aggregated_data / get_fitness_data response."""

    @property
    def data_items(self) -> list[AggregatedDataItem]:
        """Parse the list of data items."""
        return _parse_model_list(self.result.get("data_list"), AggregatedDataItem)

    @property
    def has_more(self) -> bool:
        """Whether there is more data."""
        return _coerce_bool(self.result.get("has_more", False))

    @property
    def next_key(self) -> str:
        """Start key of the next page."""
        value = self.result.get("next_key", "")
        return str(value) if value is not None else ""


# endregion


# region Relative management API responses
class VerifyUserResponse(_DictResultResponse):
    """verify_userinfo_by_id response."""

    @property
    def user_info(self) -> VerifiedUserInfo | None:
        """Parse the user info; returns None if not found."""
        if not self.result or not self.result.get("userId"):
            return None
        return VerifiedUserInfo.model_validate(self.result)


class InviteResponse(_DictResultResponse):
    """send_invite response."""

    @property
    def success(self) -> bool:
        """Whether the invite was sent successfully."""
        return _coerce_int(self.result.get("send_ret"), default=0) == 1


class OperateInviteResponse(_DictResultResponse):
    """operate_invite response (accept/reject invite)."""

    @property
    def success(self) -> bool:
        """Whether the operation succeeded."""
        return _coerce_bool(self.result.get("operate_ret"))


class DeleteRelativeResponse(_DictResultResponse):
    """delete_relative response."""

    @property
    def success(self) -> bool:
        """Whether the deletion succeeded."""
        return _coerce_bool(self.result.get("delete_ret"))


class SharedDataTypesResponse(_DictResultResponse):
    """get_shared_data_types response."""

    @property
    def keys(self) -> list[str]:
        """List of shareable data types."""
        return _coerce_str_list(self.result.get("keys"))


class InviteUniqueIdResponse(_DictResultResponse):
    """get_invite_unique_id response."""

    @property
    def invite_link_id(self) -> int:
        """QR code invite link ID."""
        return _coerce_int(self.result.get("invite_link_id"), default=0)


class FamilyMemberResponse(_DictResultResponse):
    """get_family_member response."""

    @property
    def family_user_list(self) -> list[dict[str, Any]]:
        """Family member list (raw dicts)."""
        return _coerce_dict_list(self.result.get("family_user_list"))


# endregion


# region Messages
class InviteMessage(BaseModel):
    """Relative invite message (from the get_msg_list response).

    Attributes:
        msg_id: Message ID (used by operate_invite).
        module: Message module (1 = relatives).
        type: Message type (1 = pending invite, 5 = historical notification).
        receiver: Receiver UID.
        sender: Sender UID.
        extra_data: JSON string containing invite_id, nick_name, icon, etc.
        is_new: Whether the message is new.
        data_status: Data status (0 = pending, 1 = handled).
        create_time: Creation timestamp.
    """

    msg_id: int = 0
    module: int = 0
    type: int = 0
    receiver: int = 0
    sender: int = 0
    extra_data: str = ""
    is_new: int = 0
    data_status: int = 0
    create_time: int = 0
    last_modify: int = 0

    @field_validator("extra_data", mode="before")
    @classmethod
    def _normalize_extra_data(cls, value: Any) -> str:
        """Make sure extra_data is always a JSON string before parsing."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value) if value is not None else ""

    @cached_property
    def _parsed_extra(self) -> dict[str, Any]:
        """Parse the extra_data JSON (result is cached)."""
        try:
            parsed = json.loads(self.extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def invite_id(self) -> int | None:
        """Parse invite_id from extra_data (only present when type=1)."""
        return _coerce_optional_int(self._parsed_extra.get("invite_id"))

    @property
    def nick_name(self) -> str:
        """Parse the nickname from extra_data."""
        return self._parsed_extra.get("nick_name", "")

    @property
    def icon(self) -> str:
        """Parse the avatar URL from extra_data."""
        return self._parsed_extra.get("icon", "")

    @property
    def is_pending(self) -> bool:
        """Whether this is a pending invite."""
        return self.type == 1 and self.data_status == 0


class MessageListResponse(_DictResultResponse):
    """get_msg_list response."""

    @property
    def messages(self) -> list[InviteMessage]:
        """Message list."""
        return _parse_model_list(self.result.get("messages"), InviteMessage)

    @property
    def msg_total(self) -> int:
        """Total number of messages."""
        return _coerce_int(self.result.get("msg_total"), default=0)


class CheckNewMsgResponse(_ListResultResponse):
    """check_new_msg response."""

    def has_new(self, module: int = 1) -> bool:
        """Whether the given module has new messages."""
        for item in self.result:
            if _coerce_int(item.get("module"), default=0) == module and _coerce_bool(
                item.get("is_new")
            ):
                return True
        return False


# endregion
