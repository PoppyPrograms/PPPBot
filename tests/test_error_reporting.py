import logging
import os
import unittest
from unittest.mock import Mock, patch

from error_reporting import (
	ErrorReporter,
	ErrorWebhookLogHandler,
	redact_secrets,
	split_discord_message,
)


class ErrorReportingTests(unittest.TestCase):
	def test_redacts_configured_credentials_and_discord_tokens(self):
		with patch.dict(
			os.environ,
			{
				"DISCORD_TOKEN": "discord-token-value",
				"LOGS_CHANNEL_WEBHOOK_URL": "https://discord.com/api/webhooks/123/secret-value",
			},
			clear=False,
		):
			text = (
				"token=discord-token-value "
				"url=https://discord.com/api/webhooks/123/secret-value"
			)
			redacted = redact_secrets(text)

		self.assertNotIn("discord-token-value", redacted)
		self.assertNotIn("secret-value", redacted)
		self.assertIn("[REDACTED]", redacted)

	def test_splits_messages_at_discord_limit(self):
		content = "first\n" + ("x" * 25) + "\nlast"
		chunks = split_discord_message(content, limit=16)

		self.assertEqual("".join(chunks), content)
		self.assertTrue(all(len(chunk) <= 16 for chunk in chunks))
		self.assertGreater(len(chunks), 1)

	def test_duplicate_exception_is_suppressed_without_network_access(self):
		reporter = ErrorReporter(
			"https://discord.com/api/webhooks/123/secret-value",
			dedupe_seconds=60,
		)
		try:
			raise ValueError("bad value")
		except ValueError as exception:
			first = reporter.report_exception(exception, context="first")
			second = reporter.report_exception(exception, context="second")

		self.assertTrue(first)
		self.assertFalse(second)
		self.assertEqual(len(reporter._pending), 1)

	def test_disabled_reporter_is_a_noop(self):
		reporter = ErrorReporter(None)

		self.assertFalse(reporter.report_message("message"))
		self.assertEqual(len(reporter._pending), 0)

	def test_logging_handler_forwards_error_records(self):
		reporter = Mock()
		handler = ErrorWebhookLogHandler(reporter)
		record = logging.LogRecord(
			name="test",
			level=logging.ERROR,
			pathname=__file__,
			lineno=1,
			msg="something failed",
			args=(),
			exc_info=None,
		)

		handler.emit(record)

		reporter.report_message.assert_called_once_with(
		"something failed", context="Logger 'test' emitted ERROR"
	)


if __name__ == "__main__":
	unittest.main()
