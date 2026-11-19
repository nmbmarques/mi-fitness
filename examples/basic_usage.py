"""Usage example — log in and query a relative's health data.

Before running, make sure that:
1. You have added the relative relationship in the Mi Fitness app
2. The relative has authorised data sharing in the app

Usage:
    uv run python examples/basic_usage.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mi_fitness import MiHealthClient, XiaomiAuth

TOKEN_PATH = Path("token.json")


async def main() -> None:
    # region Login (needed on first run)
    if not TOKEN_PATH.exists():
        print("First run, please scan the QR code to log in:")
        async with XiaomiAuth() as auth:
            await auth.login_qr()
            auth.save_token(TOKEN_PATH)
            print(f"Login succeeded! Token saved to {TOKEN_PATH}")
    # endregion

    # region Query data (create the client in one step)
    async with MiHealthClient.from_token(TOKEN_PATH) as client:
        # 1. Get the list of relatives
        relatives = await client.get_relatives()
        print(f"\n{len(relatives)} relative(s) linked:")
        for r in relatives:
            print(f"  - [{r.relative_uid}] {r.relative_note or '(no note set)'}")

        if not relatives:
            print("No relatives found; add a relative relationship in the app first")
            return

        # 2. Query the most recently synced data of the first relative
        target = relatives[0]
        uid = target.relative_uid
        print(f"\nMost recently synced health data for [{target.relative_note}] (UID: {uid}):")

        latest = await client.get_latest_data(uid)
        print(f"  Available metrics: {', '.join(latest.available_keys)}")

        if latest.heart_rate:
            print(f"  Latest heart rate: {latest.heart_rate.bpm} bpm")
        if latest.sleep:
            print(
                f"  Latest sleep: {latest.sleep.total_duration} min, score {latest.sleep.sleep_score}/100"
            )
        if latest.steps:
            print(
                f"  Latest steps: {latest.steps.steps} steps / {latest.steps.distance} m / {latest.steps.calories} kcal"
            )
        if latest.weight:
            print(f"  Latest weight: {latest.weight.weight}kg BMI {latest.weight.bmi}")

        summary = await client.get_latest_daily_summary(uid)
        print(f"\nMost recent synced daily summary ({summary.date}):")
        print(f"  Heart rate: {summary.heart_rate or 'No data yet'}")
        print(f"  Sleep: {summary.sleep or 'No data yet'}")
        print(f"  Steps: {summary.steps or 'No data yet'}")
    # endregion


if __name__ == "__main__":
    asyncio.run(main())
