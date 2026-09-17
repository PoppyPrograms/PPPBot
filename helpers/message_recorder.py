"""Collect recent Discord messages and forward them to the request recorder.

The recorder is deliberately implemented with the Python standard library so
the bot does not need another runtime dependency. Discord history failures and
recorder connection failures are isolated from the bot's other work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Iterable


REQUEST_RECORDER_URL = "http://request-recorder:8080/incoming"
REQUEST_TIMEOUT_SECONDS = 5
MESSAGE_RECORDER_INTERVAL_SECONDS = 60 * 60

logger = logging.getLogger("pppbot.message_recorder")


def _id(value: Any) -> str | None:
	"""Return Discord IDs as strings, which are safe for JSON consumers."""

	if value is None:
		return None
	return str(value)


def _isoformat(value: Any) -> str | None:
	if value is None:
		return None
	if hasattr(value, "isoformat"):
		return value.isoformat()
	return str(value)


def _enum_name(value: Any) -> str | None:
	if value is None:
		return None
	return getattr(value, "name", None) or str(value)


def _safe_attr(value: Any, name: str, default: Any = None) -> Any:
	"""Read optional Discord properties without losing the whole message."""

	try:
		return getattr(value, name, default)
	except Exception:
		return default


def _safe_call(function: Any, default: Any = None) -> Any:
	if not callable(function):
		return default
	try:
		return function()
	except Exception:
		return default


def _json_safe(value: Any) -> Any:
	"""Convert Discord model values to values accepted by ``json.dumps``."""

	if value is None or isinstance(value, (str, int, float, bool)):
		return value
	if isinstance(value, datetime):
		return value.isoformat()
	if isinstance(value, dict):
		return {str(key): _json_safe(item) for key, item in value.items()}
	if isinstance(value, (list, tuple, set)):
		return [_json_safe(item) for item in value]
	return str(value)


def _user_context(user: Any) -> dict[str, Any] | None:
	if user is None:
		return None

	return {
		"id": _id(getattr(user, "id", None)),
		"name": getattr(user, "name", None),
		"display_name": getattr(user, "display_name", None),
		"global_name": getattr(user, "global_name", None),
		"mention": getattr(user, "mention", None),
		"bot": getattr(user, "bot", None),
	}


def _role_context(role: Any) -> dict[str, Any] | None:
	if role is None:
		return None

	return {
		"id": _id(getattr(role, "id", None)),
		"name": getattr(role, "name", None),
		"mention": getattr(role, "mention", None),
		"position": getattr(role, "position", None),
	}


def _channel_summary(channel: Any) -> dict[str, Any] | None:
	if channel is None:
		return None

	channel_type = _safe_attr(channel, "type")
	parent = _safe_attr(channel, "parent")
	category = _safe_attr(channel, "category")
	if category is None:
		category = _safe_attr(parent, "category")
	is_news = _safe_attr(channel, "is_news")
	parent_id = _safe_attr(channel, "parent_id") or _safe_attr(parent, "id")

	return {
		"id": _id(_safe_attr(channel, "id")),
		"name": _safe_attr(channel, "name"),
		"type": _enum_name(channel_type),
		"topic": _safe_attr(channel, "topic"),
		"nsfw": _safe_attr(channel, "nsfw"),
		"position": _safe_attr(channel, "position"),
		"parent_id": _id(parent_id),
		"parent_name": _safe_attr(parent, "name"),
		"category_id": _id(_safe_attr(channel, "category_id") or _safe_attr(category, "id")),
		"category_name": _safe_attr(category, "name"),
		"owner_id": _id(_safe_attr(channel, "owner_id")),
		"slowmode_delay": _safe_attr(channel, "slowmode_delay"),
		"is_news": _safe_call(is_news),
		"archived": _safe_attr(channel, "archived"),
		"locked": _safe_attr(channel, "locked"),
		"invitable": _safe_attr(channel, "invitable"),
		"last_message_id": _id(_safe_attr(channel, "last_message_id")),
		"message_count": _safe_attr(channel, "message_count"),
		"total_message_sent": _safe_attr(channel, "total_message_sent"),
		"member_count": _safe_attr(channel, "member_count"),
		"created_at": _isoformat(_safe_attr(channel, "created_at")),
		"archive_timestamp": _isoformat(_safe_attr(channel, "archive_timestamp")),
		"auto_archive_duration": _safe_attr(channel, "auto_archive_duration"),
	}


def _guild_context(guild: Any) -> dict[str, Any] | None:
	if guild is None:
		return None

	return {
		"id": _id(getattr(guild, "id", None)),
		"name": getattr(guild, "name", None),
		"owner_id": _id(getattr(guild, "owner_id", None)),
		"member_count": getattr(guild, "member_count", None),
	}


def _attachment_context(attachment: Any) -> dict[str, Any]:
	is_spoiler = _safe_attr(attachment, "is_spoiler")
	return {
		"id": _id(getattr(attachment, "id", None)),
		"filename": getattr(attachment, "filename", None),
		"url": getattr(attachment, "url", None),
		"proxy_url": getattr(attachment, "proxy_url", None),
		"content_type": getattr(attachment, "content_type", None),
		"size": getattr(attachment, "size", None),
		"width": getattr(attachment, "width", None),
		"height": getattr(attachment, "height", None),
		"description": getattr(attachment, "description", None),
		"spoiler": _safe_call(is_spoiler),
		"ephemeral": _safe_attr(attachment, "ephemeral"),
		"duration": _safe_attr(attachment, "duration"),
		"title": _safe_attr(attachment, "title"),
	}


def _embed_context(embed: Any) -> Any:
	to_dict = _safe_attr(embed, "to_dict")
	if callable(to_dict):
		try:
			return _json_safe(to_dict())
		except Exception:
			logger.debug("Could not serialize a message embed", exc_info=True)
	return _json_safe(embed)


def _interaction_metadata_context(interaction: Any) -> dict[str, Any] | None:
	if interaction is None:
		return None

	modal_interaction = _safe_attr(interaction, "modal_interaction")
	return {
		"id": _id(_safe_attr(interaction, "id")),
		"type": _enum_name(_safe_attr(interaction, "type")),
		"user": _user_context(_safe_attr(interaction, "user")),
		"original_response_message_id": _id(
			_safe_attr(interaction, "original_response_message_id")
		),
		"interacted_message_id": _id(_safe_attr(interaction, "interacted_message_id")),
		"target_user": _user_context(_safe_attr(interaction, "target_user")),
		"target_message_id": _id(_safe_attr(interaction, "target_message_id")),
		"modal_interaction": _interaction_metadata_context(modal_interaction),
	}


def _reaction_context(reaction: Any) -> dict[str, Any]:
	emoji = getattr(reaction, "emoji", None)
	return {
		"count": getattr(reaction, "count", None),
		"me": getattr(reaction, "me", None),
		"burst_count": getattr(reaction, "burst_count", None),
		"emoji": {
			"name": getattr(emoji, "name", None) or str(emoji),
			"id": _id(getattr(emoji, "id", None)),
			"animated": getattr(emoji, "animated", None),
		},
	}


def _sticker_context(sticker: Any) -> dict[str, Any]:
	return {
		"id": _id(getattr(sticker, "id", None)),
		"name": getattr(sticker, "name", None),
		"format": _enum_name(getattr(sticker, "format", None)),
		"url": getattr(sticker, "url", None),
	}


def _resolved_message_context(message: Any) -> dict[str, Any] | None:
	if message is None:
		return None

	return {
		"id": _id(getattr(message, "id", None)),
		"author": _user_context(getattr(message, "author", None)),
		"content": getattr(message, "content", None),
		"created_at": _isoformat(getattr(message, "created_at", None)),
		"jump_url": getattr(message, "jump_url", None),
	}


def _reference_context(reference: Any) -> dict[str, Any] | None:
	if reference is None:
		return None

	return {
		"message_id": _id(getattr(reference, "message_id", None)),
		"channel_id": _id(getattr(reference, "channel_id", None)),
		"guild_id": _id(getattr(reference, "guild_id", None)),
		"type": _enum_name(getattr(reference, "type", None)),
		"fail_if_not_exists": getattr(reference, "fail_if_not_exists", None),
		"resolved": _resolved_message_context(getattr(reference, "resolved", None)),
	}


def serialize_message(message: Any) -> dict[str, Any]:
	"""Serialize a Discord message while retaining useful surrounding context."""

	author = getattr(message, "author", None)
	channel = getattr(message, "channel", None)
	guild = getattr(message, "guild", None) or getattr(channel, "guild", None)

	return {
		"id": _id(getattr(message, "id", None)),
		"guild": _guild_context(guild),
		"guild_id": _id(getattr(guild, "id", None)),
		"channel": _channel_summary(channel),
		"channel_id": _id(getattr(channel, "id", None)),
		"channel_name": getattr(channel, "name", None),
		"author": _user_context(author),
		"author_id": _id(getattr(author, "id", None)),
		"content": getattr(message, "content", None),
		"clean_content": getattr(message, "clean_content", None),
		"system_content": getattr(message, "system_content", None),
		"created_at": _isoformat(getattr(message, "created_at", None)),
		"edited_at": _isoformat(getattr(message, "edited_at", None)),
		"jump_url": getattr(message, "jump_url", None),
		"pinned": getattr(message, "pinned", None),
		"pinned_at": _isoformat(getattr(message, "pinned_at", None)),
		"tts": getattr(message, "tts", None),
		"type": _enum_name(getattr(message, "type", None)),
		"mention_everyone": getattr(message, "mention_everyone", None),
		"position": getattr(message, "position", None),
		"flags": getattr(getattr(message, "flags", None), "value", None),
		"webhook_id": _id(getattr(message, "webhook_id", None)),
		"application_id": _id(getattr(message, "application_id", None)),
		"nonce": _id(getattr(message, "nonce", None)),
		"author_is_bot": getattr(author, "bot", None),
		"mentions": [
			_user_context(mentioned_user)
			for mentioned_user in getattr(message, "mentions", ())
		],
		"role_mentions": [
			_role_context(mentioned_role)
			for mentioned_role in getattr(message, "role_mentions", ())
		],
		"channel_mentions": [
			_channel_summary(mentioned_channel)
			for mentioned_channel in getattr(message, "channel_mentions", ())
		],
		"attachments": [
			_attachment_context(attachment)
			for attachment in getattr(message, "attachments", ())
		],
		"embeds": [
			_embed_context(embed) for embed in getattr(message, "embeds", ())
		],
		"reactions": [
			_reaction_context(reaction)
			for reaction in getattr(message, "reactions", ())
		],
		"stickers": [
			_sticker_context(sticker)
			for sticker in getattr(message, "stickers", ())
		],
		"components": [
			_embed_context(component)
			for component in getattr(message, "components", ())
		],
		"poll": _embed_context(getattr(message, "poll", None))
		if getattr(message, "poll", None) is not None
		else None,
		"interaction_metadata": _interaction_metadata_context(
			getattr(message, "interaction_metadata", None)
		),
		"reference": _reference_context(getattr(message, "reference", None)),
	}


def _messageable_channels(client: Any) -> Iterable[Any]:
	"""Yield accessible guild, thread, and known private channels once each."""

	seen_channel_ids: set[str] = set()

	def add_channels(channels: Iterable[Any]) -> Iterable[Any]:
		for channel in channels or ():
			history = getattr(channel, "history", None)
			if not callable(history):
				continue
			channel_id = _id(getattr(channel, "id", None))
			if channel_id is not None and channel_id in seen_channel_ids:
				continue
			if channel_id is not None:
				seen_channel_ids.add(channel_id)
			yield channel

	for guild in getattr(client, "guilds", ()):
		yield from add_channels(getattr(guild, "channels", ()))
		yield from add_channels(getattr(guild, "threads", ()))

	# Discord cannot enumerate private channels the bot has never encountered.
	yield from add_channels(getattr(client, "private_channels", ()))


async def _messageable_channels_with_archived(
	client: Any,
	window_start: datetime,
	window_end: datetime,
) -> AsyncIterator[Any]:
	"""Yield base channels plus archived threads that could contain this window."""

	seen_channel_ids: set[str] = set()

	def add_channel(channel: Any) -> Any:
		history = _safe_attr(channel, "history")
		if not callable(history):
			return None
		channel_id = _id(_safe_attr(channel, "id"))
		if channel_id is not None and channel_id in seen_channel_ids:
			return None
		if channel_id is not None:
			seen_channel_ids.add(channel_id)
		return channel

	for channel in _messageable_channels(client):
		channel = add_channel(channel)
		if channel is not None:
			yield channel

	for guild in getattr(client, "guilds", ()):
		for parent in getattr(guild, "channels", ()):
			archived_threads = _safe_attr(parent, "archived_threads")
			if not callable(archived_threads):
				continue

			try:
				threads = archived_threads(limit=None, before=window_end)
				async for thread in threads:
					archive_timestamp = _safe_attr(thread, "archive_timestamp")
					if archive_timestamp is not None:
						try:
							if _as_utc(archive_timestamp) < window_start:
								# Discord returns archived threads newest first.
								break
						except (TypeError, ValueError):
							pass

					thread = add_channel(thread)
					if thread is not None:
						yield thread
			except Exception as error:
				# Archived-thread endpoints need separate permissions and are not
				# available for every channel type; continue with what is accessible.
				logger.debug(
					"Could not enumerate archived threads for channel %s: %s",
					_id(_safe_attr(parent, "id")),
					error,
				)


async def collect_recent_messages(
	client: Any,
	window_start: datetime,
	window_end: datetime,
) -> list[dict[str, Any]]:
	"""Read the previous hour from every accessible messageable channel."""

	messages: list[dict[str, Any]] = []
	seen_message_ids: set[str] = set()

	async for channel in _messageable_channels_with_archived(
		client,
		window_start,
		window_end,
	):
		try:
			history = channel.history(
				after=window_start,
				before=window_end,
				oldest_first=True,
				limit=None,
			)
			async for message in history:
				message_id = _id(getattr(message, "id", None))
				if message_id is not None and message_id in seen_message_ids:
					continue
				if message_id is not None:
					seen_message_ids.add(message_id)
				messages.append(serialize_message(message))
		except Exception as error:
			# Permission errors, deleted channels, and transient Discord failures
			# should not stop collection from the remaining channels.
			logger.debug(
				"Could not collect messages from channel %s: %s",
				_id(getattr(channel, "id", None)),
				error,
			)

	messages.sort(key=lambda message: message.get("created_at") or "")
	return messages


def post_messages(
	messages: Iterable[dict[str, Any]],
	url: str = REQUEST_RECORDER_URL,
) -> bool:
	"""POST one batch to request-recorder, returning false on network failure."""

	payload = json.dumps(
		{"messages": list(messages)},
		ensure_ascii=False,
		default=_json_safe,
	).encode("utf-8")
	request = urllib.request.Request(
		url,
		data=payload,
		headers={"Content-Type": "application/json"},
		method="POST",
	)

	try:
		with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
			# Consume the response so the connection can be closed and reused.
			response.read()
	except (
		urllib.error.HTTPError,
		urllib.error.URLError,
		TimeoutError,
		OSError,
		ValueError,
	) as error:
		logger.debug("Request recorder unavailable: %s", error)
		return False

	return True


def _as_utc(value: datetime) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)


async def collect_and_send_recent_messages(
	client: Any,
	now: datetime | None = None,
) -> dict[str, Any]:
	"""Collect one rolling-hour batch and send it off the event loop."""

	window_end = _as_utc(now or datetime.now(timezone.utc))
	window_start = window_end - timedelta(hours=1)
	messages = await collect_recent_messages(client, window_start, window_end)
	sent = await asyncio.to_thread(post_messages, messages)
	return {
		"count": len(messages),
		"sent": sent,
		"window_start": window_start,
		"window_end": window_end,
	}
