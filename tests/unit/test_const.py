"""Tests for constants (const.py)."""

from __future__ import annotations

from mi_fitness.const import (
    ALL_SHARED_DATA_TYPES,
    HEALTH_API_BASE,
    RELATIVES_AGGREGATED_DATA_PATH,
    RELATIVES_DELETE_PATH,
    RELATIVES_FITNESS_DATA_PATH,
    RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
    RELATIVES_GET_FAMILY_MEMBER_PATH,
    RELATIVES_GET_INVITE_ID_PATH,
    RELATIVES_GET_SHARED_TYPES_PATH,
    RELATIVES_GET_TOPIC_SUBS_PATH,
    RELATIVES_LATEST_DATA_PATH,
    RELATIVES_LIST_PATH,
    RELATIVES_SEND_INVITE_PATH,
    RELATIVES_VERIFY_USER_PATH,
    VERIFY_TYPE_XIAOMI_ID,
)


class TestAPIEndpoints:
    """API endpoint constant tests."""

    def test_base_url_is_https(self) -> None:
        assert HEALTH_API_BASE.startswith("https://")

    def test_all_paths_start_with_slash(self) -> None:
        paths = [
            RELATIVES_LIST_PATH,
            RELATIVES_LATEST_DATA_PATH,
            RELATIVES_AGGREGATED_DATA_PATH,
            RELATIVES_FITNESS_DATA_PATH,
            RELATIVES_VERIFY_USER_PATH,
            RELATIVES_SEND_INVITE_PATH,
            RELATIVES_DELETE_PATH,
            RELATIVES_GET_SHARED_TYPES_PATH,
            RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
            RELATIVES_GET_FAMILY_MEMBER_PATH,
            RELATIVES_GET_INVITE_ID_PATH,
            RELATIVES_GET_TOPIC_SUBS_PATH,
        ]
        for path in paths:
            assert path.startswith("/app/v1/relatives/"), (
                f"{path} does not start with /app/v1/relatives/"
            )


class TestSharedDataTypes:
    """Shared data type constant tests."""

    def test_has_10_types(self) -> None:
        assert len(ALL_SHARED_DATA_TYPES) == 10

    def test_contains_core_types(self) -> None:
        for key in ["heart_rate", "sleep", "steps", "weight", "spo2"]:
            assert key in ALL_SHARED_DATA_TYPES, f"Missing {key}"

    def test_no_duplicates(self) -> None:
        assert len(ALL_SHARED_DATA_TYPES) == len(set(ALL_SHARED_DATA_TYPES))


class TestVerifyTypes:
    """Verification type constant tests."""

    def test_values(self) -> None:
        assert VERIFY_TYPE_XIAOMI_ID == 1
