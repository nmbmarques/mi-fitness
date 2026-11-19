"""Xiaomi account authentication manager.

Orchestrates the login flow and token persistence. The actual login implementations are delegated to
submodules such as ``password``, ``qr`` and ``passtoken``.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Self, TypeVar

from loguru import logger

from mi_fitness.exceptions import (
    AuthError,
    CaptchaRequiredError,
    DeviceUntrustedError,
    TokenExpiredError,
)
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from . import passtoken as _pt
from . import password as _pwd
from . import qr as _qr
from . import sts as _sts
from ._helpers import create_login_http

_MAX_CAPTCHA_RETRIES = 3
_CaptchaStepT = TypeVar("_CaptchaStepT")


class XiaomiAuth:
    """Xiaomi account authentication manager.

    Handles the login flow and token persistence. Obtains ssecurity and serviceToken
    via serviceLogin; subsequent API requests are RC4-encrypted.

    Attributes:
        username: Xiaomi account (phone number or email).
        token: Current authentication credentials.
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        *,
        device_id: str = "",
    ):
        """
        Args:
            username: Xiaomi account.
            password: Password (only needed for login; never stored).
            device_id: Device identifier. Leave empty to generate a random one. A new device's first login
                triggers SMS verification, which can be handled automatically via the
                ``verification_code_handler`` callback of ``login()``.
        """
        self.username = username
        self._password = password
        self.token = AuthToken()
        if device_id:
            self.token.device_id = device_id
        self._http: RetryAsyncClient | None = None
        self._ticket_token: str = ""
        self._token_path: Path | None = None

    @classmethod
    def from_token(cls, path: Path | str) -> Self:
        """Load an existing token from a file and initialise in one step.

        Args:
            path: Token file path.

        Returns:
            An authentication manager with the token loaded.

        Raises:
            AuthError: The file does not exist or is malformed.
        """
        instance = cls()
        instance.load_token(path)
        return instance

    def _ensure_http(self) -> RetryAsyncClient:
        """Make sure the HTTP client is initialised (created lazily)."""
        if self._http is None:
            self._http = create_login_http()
        return self._http

    def _ensure_device_cookie(self) -> RetryAsyncClient:
        """Make sure a deviceId has been generated and written to the login cookies."""
        http = self._ensure_http()
        if not self.token.device_id:
            self.token.device_id = f"an_{os.urandom(16).hex()}"
        http.cookies.set("deviceId", self.token.device_id)
        return http

    async def _run_with_captcha_retries(
        self,
        http: RetryAsyncClient,
        action: Callable[[str], Awaitable[_CaptchaStepT]],
        *,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> _CaptchaStepT:
        """Handle image captcha retries uniformly."""
        captcha_code = ""
        for _ in range(_MAX_CAPTCHA_RETRIES):
            try:
                return await action(captcha_code)
            except CaptchaRequiredError as e:
                if captcha_handler is None:
                    raise
                image = await _pwd.fetch_captcha_image(http, e.captcha_url)
                captcha_code = await captcha_handler(image)
        raise AuthError(
            f"Image captcha verification failed: retried {_MAX_CAPTCHA_RETRIES} times in a row"
        )

    # region Public methods
    async def login(
        self,
        *,
        verification_code_handler: Callable[[str], Awaitable[str]] | None = None,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> AuthToken:
        """Run the full login flow.

        Args:
            verification_code_handler: SMS verification code callback. Receives the masked phone number
                (e.g. ``"191******54"``) and returns the 6-digit code the user entered.
                Called automatically when a new device's first login needs SMS verification.
                If not provided and verification is needed, ``DeviceUntrustedError`` is raised.
            captcha_handler: Image captcha callback. Receives the captcha image bytes
                (PNG/JPEG) and returns the captcha text the user recognised.
                Called automatically when the login flow triggers image captcha risk control.
                If not provided and a captcha is needed, ``CaptchaRequiredError`` is raised.

        Returns:
            The AuthToken after a successful login.

        Raises:
            AuthError: Login failed (wrong password, etc.).
            DeviceUntrustedError: SMS verification needed but no callback provided.
            CaptchaRequiredError: Image captcha needed but no callback provided.
        """
        if not self.username or not self._password:
            raise AuthError("Username and password must not be empty")

        http = self._ensure_device_cookie()

        logger.info("Starting Xiaomi account login: {}", self.username)

        sign, callback = await _pwd.get_login_page(http)

        try:
            await _pwd.submit_login(
                http,
                self.token,
                self.username,
                self._password,
                sign,
                callback,
            )
        except DeviceUntrustedError:
            if verification_code_handler is None:
                raise
            phone = await self.send_verification_code(
                captcha_handler=captcha_handler,
            )
            code = await verification_code_handler(phone)
            await self.login_with_verification_code(code)
            return self.token

        await _sts.sts_exchange(http, self.token)

        self._password = ""
        logger.info("Login succeeded, user_id={}", self.token.user_id)
        return self.token

    def save_token(self, path: Path | str) -> None:
        """Save the token to a JSON file so the next run can resume without logging in.

        Args:
            path: Save path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.token.model_dump_json(indent=2), encoding="utf-8")
        self._token_path = path
        logger.info("Token saved to {}", path)

    def load_token(self, path: Path | str) -> AuthToken:
        """Load the token from a file.

        Args:
            path: Token file path.

        Returns:
            The loaded AuthToken.

        Raises:
            AuthError: The file does not exist or is malformed.
        """
        path = Path(path)
        if not path.exists():
            raise AuthError(f"Token file does not exist: {path}")
        try:
            data = path.read_text(encoding="utf-8")
            self.token = AuthToken.model_validate_json(data)
            self._token_path = path
            logger.info("Token loaded from {}, user_id={}", path, self.token.user_id)
            return self.token
        except Exception as e:
            raise AuthError(f"Failed to parse token file: {e}") from e

    @property
    def is_authenticated(self) -> bool:
        """Check whether we are logged in."""
        return bool(self.token.service_token and self.token.ssecurity)

    @property
    def can_refresh(self) -> bool:
        """Whether the current token can be refreshed automatically."""
        return bool(self.token.pass_token and self.token.user_id)

    async def close(self) -> None:
        """Close the HTTP client (if any)."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def refresh(self) -> AuthToken:
        """Refresh serviceToken / ssecurity using the existing passToken.

        Returns:
            The refreshed AuthToken.

        Raises:
            TokenExpiredError: The current token cannot be refreshed, or the refresh failed.
        """
        if not self.can_refresh:
            raise TokenExpiredError(
                "Token has expired and passToken or user_id is missing; cannot refresh automatically"
            )

        logger.info("Refreshing login credentials, user_id={}", self.token.user_id)
        try:
            token = await self.login_passtoken(
                pass_token=self.token.pass_token,
                user_id=self.token.user_id,
                device_id=self.token.device_id,
            )
        except AuthError as e:
            raise TokenExpiredError(f"Token has expired and automatic refresh failed: {e}") from e

        if self._token_path is not None:
            self.save_token(self._token_path)

        logger.info("Login credentials refreshed, user_id={}", token.user_id)
        return token

    async def send_verification_code(
        self,
        *,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> str:
        """Send an SMS verification code to the user's phone.

        Call this after ``login()`` raises ``DeviceUntrustedError``
        to start the SMS verification flow manually.

        Args:
            captcha_handler: Image captcha callback. Receives the captcha image bytes and
                returns the captcha text the user recognised. If not provided, a captcha prompt raises
                ``CaptchaRequiredError`` directly.

        Returns:
            The masked phone number (e.g. ``"191******54"``).

        Raises:
            AuthError: Failed to get phone info or send the verification code.
            CaptchaRequiredError: Image captcha needed but no callback provided.
        """
        http = self._ensure_http()
        await _pwd.ensure_ticket_login_ready(http)

        await self._run_with_captcha_retries(
            http,
            lambda captcha_code: _pwd.send_ticket(
                http,
                self.username,
                captcha_code=captcha_code,
            ),
            captcha_handler=captcha_handler,
        )
        phone, ticket_token = await self._run_with_captcha_retries(
            http,
            lambda captcha_code: _pwd.get_phone_info(
                http,
                self.username,
                captcha_code=captcha_code,
            ),
            captcha_handler=captcha_handler,
        )

        self._ticket_token = ticket_token
        logger.info("Verification code sent to {}", phone)
        return phone

    async def login_with_verification_code(self, code: str) -> AuthToken:
        """Complete login with the SMS verification code.

        Call after ``send_verification_code()`` to submit the code the user received.

        Args:
            code: 6-digit SMS verification code.

        Returns:
            The AuthToken after a successful login.

        Raises:
            AuthError: Wrong verification code or login failed.
        """
        if not self._ticket_token:
            raise AuthError("Call send_verification_code() first to send a verification code")

        http = self._ensure_http()
        http.cookies.set("ticketToken", self._ticket_token)

        sign, callback = await _pwd.get_login_page(http, login_sign="ticket")
        await _pwd.submit_ticket_auth(http, self.token, code, sign, callback)
        await _sts.sts_exchange(http, self.token)

        self._password = ""
        self._ticket_token = ""
        logger.info("SMS verification code login succeeded, user_id={}", self.token.user_id)
        return self.token

    def __repr__(self) -> str:
        status = "authenticated" if self.is_authenticated else "not authenticated"
        uid = self.token.user_id or "N/A"
        return f"XiaomiAuth(user={self.username or uid!r}, {status})"

    async def login_qr(
        self,
        *,
        qr_callback: Callable[[str, str], Awaitable[None]] | None = None,
        poll_interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> AuthToken:
        """QR code login (no password needed; avoids captcha risk control).

        The user scans the QR code with the Xiaomi account app to log in; the SDK long-polls
        for the scan result and extracts the credentials automatically.

        Args:
            qr_callback: Callback to display the QR code. Receives ``(qr_image_url, login_url)``,
                where ``qr_image_url`` is the QR code image URL (can be downloaded and shown) and
                ``login_url`` is an alternative browser login link.
                By default the info is printed to the console.
            poll_interval: Long-polling interval (seconds).
            max_wait: QR scan timeout (seconds).

        Returns:
            The AuthToken after a successful login.

        Raises:
            AuthError: Failed to get the QR code, or the scan timed out.
        """
        http = self._ensure_device_cookie()

        await _qr.login_qr(
            http,
            self.token,
            qr_callback=qr_callback,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

        await _sts.sts_exchange(http, self.token)

        logger.info("QR code login succeeded, user_id={}", self.token.user_id)
        return self.token

    async def login_passtoken(
        self,
        *,
        pass_token: str = "",
        user_id: str = "",
        device_id: str = "",
    ) -> AuthToken:
        """Exchange a passToken for full login credentials (no password needed).

        The passToken can be obtained via ``migate.get_passtoken()`` or extracted from the cookies
        after logging in to your Xiaomi account in a browser. This method calls ``serviceLogin`` with the passToken
        to obtain ``ssecurity`` and ``serviceToken``.

        Args:
            pass_token: Xiaomi account passToken.
            user_id: Xiaomi account userId.
            device_id: Device identifier (optional).

        Returns:
            The AuthToken after a successful login.

        Raises:
            AuthError: The passToken is invalid or the credential exchange failed.
        """
        http = self._ensure_http()

        await _pt.login_passtoken(
            http,
            self.token,
            pass_token=pass_token,
            user_id=user_id,
            device_id=device_id,
        )

        await _sts.sts_exchange(http, self.token)

        logger.info("passToken login succeeded, user_id={}", self.token.user_id)
        return self.token

    # endregion

    # region Context manager
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # endregion
