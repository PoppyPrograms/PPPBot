import asyncio
import glob
import logging
import os
import sys
import time

from error_reporting import (
	ErrorReporter,
	ErrorWebhookLogHandler,
	set_default_reporter,
)


# Configure reporting before loading command modules so import-time failures are
# reported too. The reporter is optional when the environment variable is not
# configured, and normal stderr/Docker logging remains available either way.
error_reporter = ErrorReporter(os.getenv("LOGS_CHANNEL_WEBHOOK_URL"))
logging.getLogger().addHandler(ErrorWebhookLogHandler(error_reporter))
set_default_reporter(error_reporter)
error_reporter.install()

import discord
import env
from discord import app_commands
from discord.ext import commands


from storage import close_expired_auctions, initialize_database
from helpers.message_recorder import (
	MESSAGE_RECORDER_INTERVAL_SECONDS,
	collect_and_send_recent_messages,
)


initialize_database()

modules = []
on_message_handlers = []
for m in glob.glob("commands/*.py"):
	module = __import__(m[:-3].replace("/","."), globals(), locals(), ["*"], 0)
	modules.append(module)

logger = logging.getLogger("pppbot")


class PPPBot(commands.Bot):
	async def setup_hook(self):
		await error_reporter.start()
		for module in modules:
			load_module(module)

		# Sync before the gateway starts dispatching interactions. Rebuilding the
		# tree in on_ready created a small window where valid commands looked
		# unknown, especially after reconnects.
		await self.tree.sync()
		self.tree.copy_global_to(guild=guild)
		await self.tree.sync(guild=guild)
		await super().setup_hook()

	async def close(self):
		await error_reporter.stop()
		await super().close()


guild = discord.Object(id=env.GUILD_ID)
intents = discord.Intents.all()
intents.message_content = True
client = PPPBot(command_prefix="&", intents=intents)
client.tree.fallback_to_global = True
auction_watcher_task = None
message_recorder_task = None


async def watch_expired_auctions():
	await client.wait_until_ready()
	while not client.is_closed():
		try:
			outcomes = close_expired_auctions()
			for outcome in outcomes:
				channel = client.get_channel(int(outcome["channel_id"]))
				if channel is None:
					try:
						channel = await client.fetch_channel(int(outcome["channel_id"]))
					except discord.DiscordException:
						continue

				if outcome["status"] == "sold":
					message = (
						f"Auction #{outcome['listing_id']} ended — "
						f"<@{outcome['winner_id']}> won collectible "
						f"#{outcome['item_id']} for {outcome['amount']} burgas <:burga:1493907112542077092>"
					)
				else:
					message = (
						f"Auction #{outcome['listing_id']} ended without a winning bid 🙁"
					)
				await channel.send(
					message,
					allowed_mentions=discord.AllowedMentions.none(),
				)
			await asyncio.sleep(30)
		except Exception as error:
			print("auction watcher error: %s" % error)
			await asyncio.sleep(30)


async def record_recent_messages():
	"""Forward a rolling hour of accessible messages once per hour."""

	await client.wait_until_ready()
	while not client.is_closed():
		started = time.monotonic()
		try:
			result = await collect_and_send_recent_messages(client)
			logger.debug(
				"Message recorder batch: %s messages, sent=%s",
				result["count"],
				result["sent"],
			)
		except asyncio.CancelledError:
			raise
		except Exception as error:
			# A recorder failure must never take down the bot or the hourly loop.
			logger.debug("Message recorder batch failed: %s", error, exc_info=True)

		remaining = MESSAGE_RECORDER_INTERVAL_SECONDS - (time.monotonic() - started)
		if remaining > 0:
			await asyncio.sleep(remaining)


def report_discord_error(context, exception, tb=None):
	if not isinstance(exception, BaseException):
		exception = RuntimeError(str(exception))

	error_reporter.report_exception(exception, context=context, tb=tb)
	logger.error(
		"%s",
		context,
		exc_info=(type(exception), exception, tb or exception.__traceback__),
	)


@client.event
async def on_error(event_method, *args, **kwargs):
	"""Report exceptions raised by Discord event callbacks."""

	_, exception, tb = sys.exc_info()
	if exception is None:
		exception = RuntimeError(
			f"Discord event '{event_method}' failed without an exception object"
		)
		report_discord_error(
			f"Discord event '{event_method}'",
			exception,
			tb,
		)
		return

	report_discord_error(f"Discord event '{event_method}'", exception, tb)


@client.event
async def on_command_error(context, exception):
	"""Report errors from traditional prefix commands as well."""

	command = getattr(context, "command", None)
	command_name = getattr(command, "qualified_name", None) or str(command or "unknown")
	report_discord_error(
		f"Prefix command '{command_name}'",
		exception,
		getattr(exception, "__traceback__", None),
	)


async def on_app_command_error(interaction, exception):
	"""Report errors from slash and context-menu commands."""

	command = getattr(interaction, "command", None)
	data = getattr(interaction, "data", {}) or {}
	command_name = (
		getattr(command, "qualified_name", None)
		or getattr(command, "name", None)
		or data.get("name", "unknown")
	)
	report_discord_error(
		f"Application command '{command_name}'",
		exception,
		getattr(exception, "__traceback__", None),
	)


# CommandTree has its own error hook; registering the client event alone does
# not catch application-command invocation errors.
client.tree.on_error = on_app_command_error

@client.event
async def on_ready():
	global auction_watcher_task, message_recorder_task
	if auction_watcher_task is None or auction_watcher_task.done():
		auction_watcher_task = asyncio.create_task(watch_expired_auctions())
	if message_recorder_task is None or message_recorder_task.done():
		message_recorder_task = asyncio.create_task(record_recent_messages())

@client.event
async def on_message(message):
	for handler in on_message_handlers:
		r = await handler(message)
		if r is True:  # return True to signal message capture
			return


def load_module_descriptor(module, descriptor):
	if "type" not in descriptor:
		print("MISSING module.type ATTRIBUTE IN %s" % str(module))
		return

	type = descriptor["type"].lower()
	match type:
		case "command":
			if ("name" not in descriptor) or ("callback" not in descriptor):
				print("MISSING module.name OR module.callback ATTRIBUTE IN %s" % str(module))
				return
			name = descriptor["name"]
			callback = descriptor["callback"]
			description = descriptor["description"] if "description" in descriptor else "..."
			nsfw = bool(descriptor["nsfw"]) if "nsfw" in descriptor else False
			print("registerd /%s" % name)
			client.tree.add_command(
				app_commands.Command(
					name=name,
					description=description,
					callback=callback,
					nsfw=nsfw,
				)
			)
			return

		case "context_menu" | "contextmenu":
			if ("name" not in descriptor) or ("callback" not in descriptor):
				print("MISSING module.name OR module.callback ATTRIBUTE IN %s" % str(module))
				return
			name = descriptor["name"]
			callback = descriptor["callback"]
			nsfw = bool(descriptor["nsfw"]) if "nsfw" in descriptor else False
			print("registerd /%s" % name)
			client.tree.add_command(
				app_commands.ContextMenu(name=name, callback=callback, nsfw=nsfw)
			)
			return

		case "onmessage" | "on_message" | "messagehandler" | "message_handler" | "message":
			if "callback" not in descriptor:
				print("MISSING module.callback ATTRIBUTE IN %s" % str(module))
				return
			on_message_handlers.append(descriptor["callback"])
			return


def load_module(module):
	if hasattr(module, "modules"):
		for descriptor in module.modules:
			load_module_descriptor(module, descriptor)

	if not hasattr(module, "module"):
		return  # no longer required

	if "type" not in module.module:
		print("MISSING module.type ATTRIBUTE IN %s" % str(module))
		return

	load_module_descriptor(module, module.module)
client.run(env.BOT_TOKEN)
