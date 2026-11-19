# Mi Fitness (archive mirror)

A Python SDK for Xiaomi Mi Fitness that reads health data — heart rate, sleep, steps and more — from other accounts in your relatives (family sharing) list.

> **⚠️ For learning and testing only.** The API endpoints may change with app updates.
>
> **📦 This repository is an archive mirror.** The original repository `MistEO/MiSDK` was deleted from GitHub; this repository keeps a copy of the source. All code and commit history come from the original author [Misty02600](https://github.com/MistEO). Please respect the original author's copyright and the GPL-3.0 licence.
>
> **🌐 English translation.** This fork translates the README, docstrings, comments and messages from Chinese to English. Behaviour is unchanged.

## Installation

```bash
pip install mi-fitness
# or with uv
uv add mi-fitness
```

Install from source:

```bash
git clone https://github.com/nmbmarques/mi-fitness.git && cd mi-fitness
uv sync
```

## Quick start

### Login (QR code)

Log in by scanning a QR code with your Xiaomi account app:

```python
import asyncio
from mi_fitness import XiaomiAuth


async def login():
    async with XiaomiAuth() as auth:
        await auth.login_qr()
        auth.save_token("token.json")
        print(f"Login succeeded! user_id = {auth.token.user_id}")


asyncio.run(login())
```

Custom QR code display callback:

```python
async def login_with_callback():
    async def on_qr(qr_image_url: str, login_url: str) -> None:
        # qr_image_url is the URL of the QR code image
        print(f"Please scan: {qr_image_url}")

    async with XiaomiAuth() as auth:
        await auth.login_qr(qr_callback=on_qr)
        auth.save_token("token.json")
```

One-line CLI login:

```bash
uv run python -m mi_fitness.cli qr-login
```

### Querying data

```python
import asyncio
from mi_fitness import MiHealthClient


async def main():
    async with MiHealthClient.from_token("token.json") as client:
        # List of relatives
        relatives = await client.get_relatives()
        for r in relatives:
            print(f"[{r.relative_uid}] {r.relative_note}")

        uid = relatives[0].relative_uid

        # Latest snapshot (strongly typed)
        latest = await client.get_latest_data(uid)
        print(latest.available_keys)
        print(latest.heart_rate)  # LatestHeartRate(bpm=84, ...)
        print(latest.steps)  # StepData(steps=3716, ...)

        # Daily summary for the most recently synced day (heart rate + sleep + steps fetched concurrently)
        summary = await client.get_latest_daily_summary(uid)
        print(f"Steps: {summary.steps}, sleep: {summary.sleep}, heart rate: {summary.heart_rate}")


asyncio.run(main())
```

### Managing relatives

```python
async def manage():
    async with MiHealthClient.from_token("token.json") as client:
        # Verify a user
        info = await client.verify_user(XIAOMI_ID)
        print(f"Found: {info.nickname} (UID: {info.user_id})")

        # Send an invite (shares all data types by default)
        await client.invite_relative(info.user_id)

        # Remove a relative
        await client.delete_relative(RELATIVE_UID)
```

### Error handling

```python
from mi_fitness import MiHealthClient, TokenExpiredError, APIError


async def safe_query():
    try:
        async with MiHealthClient.from_token("token.json") as client:
            relatives = await client.get_relatives()
    except TokenExpiredError:
        print("Token has expired; please log in again")
    except APIError as e:
        print(f"API error: {e} (HTTP {e.status_code})")
```

## API overview

### Data queries

| Method | Return type | Description |
|------|---------|------|
| `get_heart_rate(uid, date)` | `list[HeartRateData]` | Daily average / resting / max / min heart rate, latest sample |
| `get_sleep(uid, date)` | `list[SleepData]` | Duration / score / deep / light / REM / segment details |
| `get_steps(uid, date)` | `list[StepData]` | Steps / distance / calories |
| `get_calories_history(uid, date, days=1)` | `list[CaloriesData]` | Active calories by day / week |
| `get_valid_stand_history(uid, date, days=1)` | `list[ValidStandData]` | Valid stand count by day / week |
| `get_intensity_history(uid, date, days=1)` | `list[IntensityData]` | Moderate-to-vigorous activity duration by day / week |
| `get_spo2_history(uid, date, days=1)` | `list[Spo2SummaryData]` | Blood oxygen summary by day / week |
| `get_weight_history(uid, date, days=1)` | `list[WeightData]` | Weight measurements within the time window |
| `get_blood_pressure_history(uid, date, days=1)` | `list[BloodPressureData]` | Blood pressure measurements within the time window |
| `get_weight(uid)` | `WeightData \| None` | Weight / BMI |
| `get_goal(uid)` | `GoalData \| None` | Latest activity goals, with `steps_goal / calories_goal / intensity_goal` shortcuts; historical goal values are not available |
| `get_blood_pressure(uid)` | `BloodPressureData \| None` | Latest blood pressure |
| `get_calories(uid)` | `CaloriesData \| None` | Latest active calories |
| `get_valid_stand(uid)` | `ValidStandData \| None` | Latest valid stand count |
| `get_intensity(uid)` | `IntensityData \| None` | Latest moderate-to-vigorous activity duration |
| `get_spo2(uid)` | `Spo2Data \| None` | Latest blood oxygen |
| `get_latest_data(uid)` | `LatestDataSnapshot` | Strongly typed latest snapshot (goal/heart_rate/sleep/steps/weight/...) |
| `get_latest_items(uid)` | `list[LatestDataItem]` | Raw `data_list`, useful for debugging |
| `get_daily_summary(uid, date)` | `DailySummary` | Heart rate + sleep + steps fetched concurrently |
| `get_latest_daily_summary(uid)` | `DailySummary` | Automatically uses the most recently synced day, reducing empty results |
| `get_aggregated_data(uid, key, start, end)` | `AggregatedDataResponse` | Custom time range and data type |
| `get_fitness_data(uid, key, start, end)` | `AggregatedDataResponse` | Raw measurement / event data (e.g. weight, blood pressure, abnormal heart rate) |

### Relative management

| Method | Description |
|------|------|
| `get_relatives()` | Get all linked relatives |
| `find_relative(keyword)` | Find by nickname or UID |
| `verify_user(xiaomi_id)` | Verify user info before adding a relative |
| `invite_relative(uid)` | Invite a user to become a relative |
| `delete_relative(uid)` | Remove a relative relationship |
| `accept_invite(msg) / reject_invite(msg)` | Accept / reject an invite |
| `has_new_invite()` | Whether there is a new invite |
| `get_invite_link_id()` | Get the QR code invite link ID |
| `get_shared_data_types(uid)` | See which data types the other person is sharing |
| `get_family_members()` | Family group member list |

### Exceptions

| Exception | Description |
|------|------|
| `MiSDKError` | Base exception |
| `AuthError` | Authentication errors (login failure, etc.) |
| `TokenExpiredError` | Token expired and automatic refresh failed |
| `DataNotSharedError` | The relative has not shared the requested data type |
| `DataOutOfSharedTimeScopeError` | The query date is outside the time range the relative allows to be shared |
| `APIError` | Unexpected API response (includes `status_code` and `response_body`) |
| `DeviceUntrustedError` | A new device needs SMS verification |
| `CaptchaRequiredError` | Image captcha risk control triggered |
| `FamilyMemberNotFoundError` | The specified relative could not be found |
