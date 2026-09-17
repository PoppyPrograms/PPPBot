import asyncio
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from helpers.message_recorder import (
	collect_recent_messages,
	post_messages,
	serialize_message,
)


class FakeHistoryChannel:
	def __init__(self, channel_id, messages=(), error=None):
		self.id = channel_id
		self.name = f"channel-{channel_id}"
		self.type = SimpleNamespace(name="text")
		self.messages = list(messages)
		self.error = error
		self.history_args = None

	def history(self, **kwargs):
		self.history_args = kwargs

		async def iterator():
			if self.error is not None:
				raise self.error
			for message in self.messages:
				yield message

		return iterator()


class FakeArchivedParent(FakeHistoryChannel):
	def __init__(self, channel_id, archived_threads):
		super().__init__(channel_id)
		self.archived = list(archived_threads)
		self.archived_args = None

	def archived_threads(self, **kwargs):
		self.archived_args = kwargs

		async def iterator():
			for thread in self.archived:
				yield thread

		return iterator()


def make_message(message_id, channel, created_at, content="hello"):
	return SimpleNamespace(
		id=message_id,
		guild=SimpleNamespace(id=42, name="PPP", owner_id=7, member_count=3),
		channel=channel,
		author=SimpleNamespace(
			id=99,
			name="alice",
			display_name="Alice",
			global_name="Alice",
			mention="<@99>",
			bot=False,
		),
		content=content,
		clean_content=content,
		system_content=content,
		created_at=created_at,
		edited_at=None,
		jump_url=f"https://discord.test/messages/{message_id}",
		pinned=False,
		tts=False,
		type=SimpleNamespace(name="default"),
		flags=None,
		webhook_id=None,
		application_id=None,
		nonce=None,
		mentions=[],
		role_mentions=[],
		channel_mentions=[],
		attachments=[],
		embeds=[],
		reactions=[],
		stickers=[],
		reference=None,
	)


class MessageRecorderTests(unittest.TestCase):
	def test_serialize_message_includes_context_and_nested_metadata(self):
		channel = FakeHistoryChannel("channel-1")
		message = make_message(
			"message-1",
			channel,
			datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
			content="hi <@123>",
		)
		message.mentions = [SimpleNamespace(id=123, name="bob", display_name="Bob", bot=False)]
		message.role_mentions = [SimpleNamespace(id=456, name="mods", mention="<@&456>", position=2)]
		message.attachments = [
			SimpleNamespace(
				id=789,
				filename="photo.png",
				url="https://cdn.test/photo.png",
				proxy_url="https://proxy.test/photo.png",
				content_type="image/png",
				size=12,
				width=2,
				height=3,
				is_spoiler=lambda: False,
			)
		]
		message.embeds = [SimpleNamespace(to_dict=lambda: {"title": "hello"})]
		message.reactions = [
			SimpleNamespace(
				count=2,
				me=True,
				burst_count=0,
				emoji=SimpleNamespace(name="👍", id=None, animated=False),
			)
		]

		serialized = serialize_message(message)

		self.assertEqual(serialized["id"], "message-1")
		self.assertEqual(serialized["guild"]["name"], "PPP")
		self.assertEqual(serialized["channel"]["name"], "channel-channel-1")
		self.assertEqual(serialized["author"]["display_name"], "Alice")
		self.assertEqual(serialized["mentions"][0]["id"], "123")
		self.assertEqual(serialized["role_mentions"][0]["name"], "mods")
		self.assertEqual(serialized["attachments"][0]["filename"], "photo.png")
		self.assertEqual(serialized["embeds"][0]["title"], "hello")
		self.assertEqual(serialized["reactions"][0]["emoji"]["name"], "👍")

	def test_collects_guild_threads_and_known_private_channels(self):
		first_channel = FakeHistoryChannel("1")
		duplicate_channel = FakeHistoryChannel("1")
		thread_channel = FakeHistoryChannel("2")
		dm_channel = FakeHistoryChannel("3")
		created_at = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
		first_channel.messages = [make_message("first", first_channel, created_at)]
		duplicate_channel.messages = [
			make_message("duplicate", duplicate_channel, created_at)
		]
		thread_channel.messages = [make_message("thread", thread_channel, created_at)]
		dm_channel.messages = [make_message("dm", dm_channel, created_at)]
		guild = SimpleNamespace(
			channels=[first_channel, duplicate_channel],
			threads=[thread_channel],
		)
		client = SimpleNamespace(
			guilds=[guild],
			private_channels=[dm_channel],
		)
		window_start = datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc)
		window_end = datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc)

		collected = asyncio.run(
			collect_recent_messages(client, window_start, window_end)
		)

		self.assertEqual(
			[message["id"] for message in collected],
			["first", "thread", "dm"],
		)
		self.assertEqual(first_channel.history_args["after"], window_start)
		self.assertEqual(first_channel.history_args["before"], window_end)

	def test_channel_failure_does_not_abort_collection(self):
		broken = FakeHistoryChannel("broken", error=RuntimeError("not available"))
		working = FakeHistoryChannel("working")
		working.messages = [
			make_message(
				"working-message",
				working,
				datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
			)
		]
		client = SimpleNamespace(
			guilds=[SimpleNamespace(channels=[broken, working], threads=[])],
			private_channels=[],
		)

		collected = asyncio.run(
			collect_recent_messages(
				client,
				datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc),
				datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc),
			)
		)

		self.assertEqual([message["id"] for message in collected], ["working-message"])

	def test_collects_recent_archived_threads(self):
		parent = FakeArchivedParent("parent", [])
		recent_thread = FakeHistoryChannel("recent-thread")
		recent_thread.archive_timestamp = datetime(
			2026, 9, 17, 12, 30, tzinfo=timezone.utc
		)
		recent_thread.messages = [
			make_message(
				"archived-message",
				recent_thread,
				datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
			)
		]
		old_thread = FakeHistoryChannel("old-thread")
		old_thread.archive_timestamp = datetime(
			2026, 9, 17, 10, 59, tzinfo=timezone.utc
		)
		old_thread.messages = [make_message("old-message", old_thread, datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc))]
		parent.archived = [recent_thread, old_thread]
		client = SimpleNamespace(
			guilds=[SimpleNamespace(channels=[parent], threads=[])],
			private_channels=[],
		)

		collected = asyncio.run(
			collect_recent_messages(
				client,
				datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc),
				datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc),
			)
		)

		self.assertEqual([message["id"] for message in collected], ["archived-message"])
		self.assertEqual(parent.archived_args["limit"], None)
		self.assertEqual(
			parent.archived_args["before"],
			datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc),
		)

	def test_post_messages_matches_recorder_request(self):
		response = MagicMock()
		response.__enter__.return_value = response
		with patch(
			"helpers.message_recorder.urllib.request.urlopen",
			return_value=response,
		) as urlopen:
			self.assertTrue(
				post_messages(
					[{"id": "1", "content": "héllo"}],
					"http://recorder/incoming",
				)
			)

		request = urlopen.call_args.args[0]
		self.assertEqual(request.full_url, "http://recorder/incoming")
		self.assertEqual(request.get_header("Content-type"), "application/json")
		self.assertEqual(
			json.loads(request.data.decode("utf-8")),
			{"messages": [{"id": "1", "content": "héllo"}]},
		)
		response.read.assert_called_once_with()

	def test_post_messages_ignores_recorder_connection_failure(self):
		with patch(
			"helpers.message_recorder.urllib.request.urlopen",
			side_effect=urllib.error.URLError("recorder is down"),
		):
			self.assertFalse(post_messages([]))


if __name__ == "__main__":
	unittest.main()
