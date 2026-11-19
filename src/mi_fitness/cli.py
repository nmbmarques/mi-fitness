"""QR code login to obtain a token."""

from __future__ import annotations

import asyncio
from pathlib import Path

import qrcode
import qrcode.constants

from mi_fitness.auth import XiaomiAuth
from mi_fitness.exceptions import AuthError

TOKEN_FILE = Path("token.json")


def _print_qr_to_terminal(data: str) -> None:
    """Render the QR code compactly in the terminal using Unicode half-block characters."""
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    # Pad to an even number of rows
    if len(matrix) % 2:
        matrix.append([False] * len(matrix[0]))

    # Merge every two pixel rows into one character row: ▀▄█ and space represent the four combinations
    # False = white module (foreground block), True = black module (left blank as background)
    for r in range(0, len(matrix), 2):
        line: list[str] = []
        for c in range(len(matrix[0])):
            top_white = not matrix[r][c]
            bot_white = not matrix[r + 1][c]
            if top_white and bot_white:
                line.append("\u2588")  # █
            elif top_white:
                line.append("\u2580")  # ▀
            elif bot_white:
                line.append("\u2584")  # ▄
            else:
                line.append(" ")
        print("".join(line))


async def _qr_login() -> None:
    async def show_qr(qr_image_url: str, login_url: str) -> None:
        print("\n📱 Scan the QR code with the Xiaomi account app to log in\n")
        if login_url:
            _print_qr_to_terminal(login_url)
        print(f"\n   QR code image: {qr_image_url}")
        if login_url:
            print(f"   Open in browser: {login_url}")
        print("\n⏳ Waiting for scan...\n")

    async with XiaomiAuth() as auth:
        try:
            await auth.login_qr(qr_callback=show_qr)
        except AuthError as e:
            print(f"❌ QR code login failed: {e}")
            raise

        auth.save_token(TOKEN_FILE)
        print(f"✅ QR code login succeeded! user_id = {auth.token.user_id}")
        print(f"   Token saved to {TOKEN_FILE.resolve()}")


def main() -> None:
    """CLI entry point."""
    asyncio.run(_qr_login())


if __name__ == "__main__":
    main()
