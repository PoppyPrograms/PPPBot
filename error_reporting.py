"""Best-effort reporting of application errors to a Discord webhook.

The reporter is deliberately isolated from the rest of the bot.  If Discord is
unavailable, the webhook is misconfigured, or the reporter itself fails, the
original application error is still handled by the normal Python/Discord
logging paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


DISCORD_MESSAGE_LIMIT = 2000
DEFAULT_QUEUE_SIZE = 100
DEFAULT_DEDUPE_SECONDS = 30.0
DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_SYNC_TIMEOUT = 5.0
DEFAULT_FLUSH_TIMEOUT = 3.0

_SECRET_ENV_KEYS = {
    "DISCORD_TOKEN",
    "WEBHOOK_URL",
    "LOGS_CHANNEL_WEBHOOK_URL",
}
_SECRET_ENV_KEY_RE = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|WEBHOOK|PRIVATE[_-]?KEY|CREDENTIAL)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)(\b(?:DISCORD_TOKEN|WEBHOOK_URL|LOGS_CHANNEL_WEBHOOK_URL|"
    r"API[_-]?KEY|SECRET|PASSWORD|PASSWD)\b\s*[:=]\s*)[^\s,;]+"
)
_DISCORD_WEBHOOK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/api(?:/v\d+)?/"
    r"webhooks/\d+/[A-Za-z0-9._-]+",
    re.IGNORECASE,
)
_DISCORD_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{4,}\."
    r"[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
)


def _configured_secret_values() -> List[str]:
    values = []
    for key, value in os.environ.items():
        if not value:
            continue
        upper_key = key.upper()
        if upper_key not in _SECRET_ENV_KEYS and not _SECRET_ENV_KEY_RE.search(upper_key):
            continue
        if len(value) >= 4:
            values.append(value)

    return sorted(set(values), key=len, reverse=True)


def redact_secrets(value: Any) -> str:
    """Remove configured credentials and common Discord credentials from text."""

    text = str(value)
    for secret in _configured_secret_values():
        text = text.replace(secret, "[REDACTED]")

    text = _SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    text = _DISCORD_WEBHOOK_RE.sub("[REDACTED_DISCORD_WEBHOOK]", text)
    text = _DISCORD_TOKEN_RE.sub("[REDACTED_DISCORD_TOKEN]", text)
    return text


def split_discord_message(content: str, limit: int = DISCORD_MESSAGE_LIMIT) -> List[str]:
    """Split text into Discord-sized chunks, preferring newline boundaries."""

    if limit < 1:
        raise ValueError("limit must be positive")

    content = str(content)
    if not content:
        return [""]

    chunks = []
    remaining = content
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_end = limit
        else:
            split_end = split_at + 1
        chunks.append(remaining[:split_end])
        remaining = remaining[split_end:]

    if remaining:
        chunks.append(remaining)
    return chunks


def _traceback_text(
    exception: BaseException,
    tb: Optional[Any] = None,
) -> str:
    if tb is None:
        tb = getattr(exception, "__traceback__", None)
    return "".join(traceback.format_exception(type(exception), exception, tb)).rstrip()


def _report_header(context: str) -> List[str]:
    version = os.getenv("BOT_VERSION", "unknown")
    return [
        "🚨 PPP-Bot error",
        f"Context: {redact_secrets(context or 'Unhandled exception')}",
        f"Version: {redact_secrets(version)}",
        f"Host: {redact_secrets(socket.gethostname())}",
        f"Time (UTC): {datetime.now(timezone.utc).isoformat()}",
    ]


def format_exception_report(
    exception: BaseException,
    *,
    context: str = "Unhandled exception",
    tb: Optional[Any] = None,
) -> str:
    """Build a redacted, useful error report for Discord or local tests."""

    trace = redact_secrets(_traceback_text(exception, tb))
    return "\n".join(_report_header(context) + ["", "Traceback:", trace])


def format_message_report(message: str, *, context: str = "Error log") -> str:
    """Build a redacted report for an error log record without an exception."""

    return "\n".join(
        _report_header(context) + ["", "Message:", redact_secrets(message)]
    )


class ErrorReporter:
    """Queue error reports and deliver them without blocking bot callbacks."""

    def __init__(
        self,
        webhook_url: Optional[str],
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        dedupe_seconds: float = DEFAULT_DEDUPE_SECONDS,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        sync_timeout: float = DEFAULT_SYNC_TIMEOUT,
        flush_timeout: float = DEFAULT_FLUSH_TIMEOUT,
    ) -> None:
        self.webhook_url = (webhook_url or "").strip()
        self.queue_size = max(1, queue_size)
        self.dedupe_seconds = max(0.0, dedupe_seconds)
        self.request_timeout = max(0.1, request_timeout)
        self.sync_timeout = max(0.1, sync_timeout)
        self.flush_timeout = max(0.1, flush_timeout)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._session: Optional[Any] = None
        self._pending: Deque[str] = deque(maxlen=self.queue_size)
        self._fingerprints: Dict[str, float] = {}
        self._state_lock = threading.Lock()

        self._hooks_installed = False
        self._previous_sys_excepthook = None
        self._previous_threading_excepthook = None
        self._previous_loop_exception_handler = None
        self._loop_exception_handler = None

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def install(self) -> None:
        """Install process and thread hooks while preserving default behavior."""

        if self._hooks_installed:
            return

        self._previous_sys_excepthook = sys.excepthook
        sys.excepthook = self._handle_sys_exception

        if hasattr(threading, "excepthook"):
            self._previous_threading_excepthook = threading.excepthook
            threading.excepthook = self._handle_thread_exception

        self._hooks_installed = True

    async def start(self) -> None:
        """Start the async delivery worker on the bot's event loop."""

        if not self.enabled:
            return
        if self._worker_task is not None and not self._worker_task.done():
            return

        loop = asyncio.get_running_loop()
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=self.queue_size)

        try:
            import aiohttp

            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.request_timeout)
            )
        except Exception as exception:
            self._session = None
            self._write_local_failure(
                f"could not create async webhook session: {type(exception).__name__}"
            )

        self._install_loop_exception_handler(loop)
        self._worker_task = loop.create_task(
            self._worker(), name="pppbot-error-webhook-reporter"
        )

        with self._state_lock:
            pending = list(self._pending)
            self._pending.clear()
        self._enqueue_messages(pending)

    async def stop(self) -> None:
        """Flush briefly and close resources during normal bot shutdown."""

        task = self._worker_task
        queue = self._queue
        if task is None:
            return

        if queue is not None:
            try:
                await asyncio.wait_for(queue.join(), timeout=self.flush_timeout)
            except asyncio.TimeoutError:
                self._write_local_failure("timed out flushing the error webhook queue")

            if not task.done():
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

        if not task.done():
            try:
                await asyncio.wait_for(task, timeout=self.flush_timeout)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            except Exception as exception:
                self._write_local_failure(
                    f"error webhook worker stopped: {type(exception).__name__}"
                )

        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exception:
                self._write_local_failure(
                    f"could not close async webhook session: {type(exception).__name__}"
                )

        loop = self._loop
        if (
            loop is not None
            and self._loop_exception_handler is not None
            and loop.get_exception_handler() is self._loop_exception_handler
        ):
            loop.set_exception_handler(self._previous_loop_exception_handler)

        self._session = None
        self._worker_task = None
        self._queue = None
        self._loop_exception_handler = None

    def report_exception(
        self,
        exception: BaseException,
        *,
        context: str = "Unhandled exception",
        tb: Optional[Any] = None,
        immediate: bool = False,
    ) -> bool:
        """Report an exception and return whether it was queued/sent."""

        if not self.enabled:
            return False

        try:
            report = format_exception_report(exception, context=context, tb=tb)
            fingerprint_source = redact_secrets(
                f"{type(exception).__module__}.{type(exception).__qualname__}\n"
                f"{_traceback_text(exception, tb)}"
            )
            if not self._claim_fingerprint(fingerprint_source):
                return False
            self._submit(split_discord_message(report), immediate=immediate)
            return True
        except Exception as reporter_exception:
            self._write_local_failure(
                f"could not format an exception report: "
                f"{type(reporter_exception).__name__}"
            )
            return False

    def report_message(
        self,
        message: str,
        *,
        context: str = "Error log",
        immediate: bool = False,
    ) -> bool:
        """Report an error message that does not have an exception object."""

        if not self.enabled:
            return False

        try:
            report = format_message_report(message, context=context)
            if not self._claim_fingerprint(report):
                return False
            self._submit(split_discord_message(report), immediate=immediate)
            return True
        except Exception as reporter_exception:
            self._write_local_failure(
                f"could not format an error-log report: "
                f"{type(reporter_exception).__name__}"
            )
            return False

    def _claim_fingerprint(self, value: str) -> bool:
        fingerprint = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()
        now = time.monotonic()
        with self._state_lock:
            expired = [
                key
                for key, timestamp in self._fingerprints.items()
                if now - timestamp >= self.dedupe_seconds
            ]
            for key in expired:
                del self._fingerprints[key]

            previous = self._fingerprints.get(fingerprint)
            if previous is not None and now - previous < self.dedupe_seconds:
                return False
            self._fingerprints[fingerprint] = now
            return True

    def _submit(self, messages: Iterable[str], *, immediate: bool) -> None:
        if not self.enabled:
            return

        messages = list(messages)
        loop = self._loop
        if (
            loop is not None
            and not loop.is_closed()
            and loop.is_running()
            and self._queue is not None
        ):
            try:
                loop.call_soon_threadsafe(self._enqueue_messages, messages)
                return
            except RuntimeError:
                pass

        if immediate and not (
            loop is not None and not loop.is_closed() and loop.is_running()
        ):
            self._send_sync(messages)
            return

        with self._state_lock:
            self._pending.extend(messages)

    def _enqueue_messages(self, messages: Iterable[str]) -> None:
        queue = self._queue
        if queue is None:
            with self._state_lock:
                self._pending.extend(messages)
            return

        for message in messages:
            if queue.full():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self._write_local_failure("dropping an error report: queue is full")

    async def _worker(self) -> None:
        queue = self._queue
        if queue is None:
            return

        while True:
            message = await queue.get()
            try:
                if message is None:
                    return
                await self._send_async(message)
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                self._write_local_failure(
                    f"could not send error report: {type(exception).__name__}"
                )
            finally:
                queue.task_done()

    async def _send_async(self, message: str) -> None:
        session = self._session
        if session is not None:
            await self._post_with_retries(session, message)
            return

        import aiohttp

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as temporary_session:
            await self._post_with_retries(temporary_session, message)

    async def _post_with_retries(self, session: Any, message: str) -> None:
        payload = {
            "content": message,
            "allowed_mentions": {"parse": []},
        }

        for attempt in range(3):
            try:
                async with session.post(self.webhook_url, json=payload) as response:
                    if 200 <= response.status < 300:
                        return

                    if response.status == 429 or response.status >= 500:
                        if attempt < 2:
                            retry_after = response.headers.get("Retry-After", "1")
                            try:
                                delay = min(max(float(retry_after), 0.25), 5.0)
                            except (TypeError, ValueError):
                                delay = 1.0
                            await asyncio.sleep(delay)
                            continue

                    self._write_local_failure(
                        f"Discord error webhook returned HTTP {response.status}"
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                if attempt < 2:
                    await asyncio.sleep(min(2**attempt, 3))
                    continue
                self._write_local_failure(
                    f"Discord error webhook request failed: "
                    f"{type(exception).__name__}"
                )

    def _send_sync(self, messages: Iterable[str]) -> None:
        """Best-effort fallback for fatal errors before an event loop exists."""

        for message in messages:
            payload = json.dumps(
                {"content": message, "allowed_mentions": {"parse": []}}
            ).encode("utf-8")
            request = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "PPPBot-error-reporter",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.sync_timeout) as response:
                    response.read()
            except urllib.error.HTTPError as exception:
                self._write_local_failure(
                    f"Discord error webhook returned HTTP {exception.code}"
                )
            except Exception as exception:
                self._write_local_failure(
                    f"Discord error webhook request failed: "
                    f"{type(exception).__name__}"
                )

    def _install_loop_exception_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        previous = loop.get_exception_handler()
        self._previous_loop_exception_handler = previous

        def handle_loop_exception(
            current_loop: asyncio.AbstractEventLoop,
            context: Dict[str, Any],
        ) -> None:
            try:
                exception = context.get("exception")
                message = context.get("message", "Unhandled exception in event loop")
                if isinstance(exception, BaseException):
                    self.report_exception(
                        exception,
                        context=f"Asyncio loop: {message}",
                    )
                else:
                    self.report_message(
                        redact_secrets(repr(context)),
                        context=f"Asyncio loop: {message}",
                    )
            except Exception as reporter_exception:
                self._write_local_failure(
                    f"could not report an asyncio exception: "
                    f"{type(reporter_exception).__name__}"
                )

            try:
                if previous is not None:
                    previous(current_loop, context)
                else:
                    current_loop.default_exception_handler(context)
            except Exception as exception:
                self._write_local_failure(
                    f"the previous asyncio exception handler failed: "
                    f"{type(exception).__name__}"
                )

        self._loop_exception_handler = handle_loop_exception
        loop.set_exception_handler(handle_loop_exception)

    def _handle_sys_exception(self, exc_type: Any, exc_value: Any, tb: Any) -> None:
        if isinstance(exc_value, BaseException) and not isinstance(
            exc_value, (KeyboardInterrupt, SystemExit)
        ):
            try:
                self.report_exception(
                    exc_value,
                    context="Unhandled exception in the main thread",
                    tb=tb,
                    immediate=True,
                )
            except Exception as reporter_exception:
                self._write_local_failure(
                    f"could not report the main-thread exception: "
                    f"{type(reporter_exception).__name__}"
                )

        previous = self._previous_sys_excepthook
        if previous is not None and previous is not self._handle_sys_exception:
            previous(exc_type, exc_value, tb)

    def _handle_thread_exception(self, args: Any) -> None:
        exception = getattr(args, "exc_value", None)
        if isinstance(exception, BaseException) and not isinstance(
            exception, (KeyboardInterrupt, SystemExit)
        ):
            thread = getattr(args, "thread", None)
            thread_name = getattr(thread, "name", "unknown")
            try:
                self.report_exception(
                    exception,
                    context=f"Unhandled exception in thread '{thread_name}'",
                    tb=getattr(args, "exc_traceback", None),
                    immediate=True,
                )
            except Exception as reporter_exception:
                self._write_local_failure(
                    f"could not report the thread exception: "
                    f"{type(reporter_exception).__name__}"
                )

        previous = self._previous_threading_excepthook
        if previous is not None and previous is not self._handle_thread_exception:
            previous(args)

    @staticmethod
    def _write_local_failure(message: str) -> None:
        try:
            sys.stderr.write(f"[error-reporter] {redact_secrets(message)}\n")
            sys.stderr.flush()
        except BaseException:
            pass


class ErrorWebhookLogHandler(logging.Handler):
    """Forward ERROR log records while retaining the normal log handlers."""

    def __init__(self, reporter: ErrorReporter) -> None:
        super().__init__(level=logging.ERROR)
        self.reporter = reporter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            context = f"Logger '{record.name}' emitted {record.levelname}"
            exception, tb = self._exception_from_record(record)
            if exception is not None:
                self.reporter.report_exception(
                    exception,
                    context=f"{context}: {message}",
                    tb=tb,
                )
            else:
                self.reporter.report_message(message, context=context)
        except Exception as handler_exception:
            self.reporter._write_local_failure(
                f"error log handler failed: {type(handler_exception).__name__}"
            )

    @staticmethod
    def _exception_from_record(
        record: logging.LogRecord,
    ) -> Tuple[Optional[BaseException], Optional[Any]]:
        exc_info = record.exc_info
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            exception = exc_info[1]
            if isinstance(exception, BaseException):
                return exception, exc_info[2]
        elif isinstance(exc_info, BaseException):
            return exc_info, getattr(exc_info, "__traceback__", None)
        return None, None


_default_reporter: Optional[ErrorReporter] = None


def set_default_reporter(reporter: ErrorReporter) -> None:
    global _default_reporter
    _default_reporter = reporter


def report_exception(
    exception: BaseException,
    *,
    context: str = "Handled exception",
    tb: Optional[Any] = None,
    immediate: bool = False,
) -> bool:
    """Report a caught exception through the bot's configured reporter."""

    if _default_reporter is None:
        return False
    return _default_reporter.report_exception(
        exception,
        context=context,
        tb=tb,
        immediate=immediate,
    )
