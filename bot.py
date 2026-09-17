import asyncio
import discord
import glob
import env
from discord.ext import commands
from discord import app_commands

from storage import close_expired_auctions, initialize_database


initialize_database()

modules = []
on_message_handlers = []
for m in glob.glob("commands/*.py"):
	module = __import__(m[:-3].replace("/","."), globals(), locals(), ["*"], 0)
	modules.append(module)

guild=discord.Object(id=env.GUILD_ID)
intents = discord.Intents.all()
intents.message_content = True
client = commands.Bot(command_prefix="&", intents=intents)
auction_watcher_task = None


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

@client.event
async def on_ready():
	global auction_watcher_task
	client.tree.clear_commands(guild=None)
	client.tree.clear_commands(guild=guild)
	on_message_handlers.clear()

	for module in modules:
		load_module(module)

	await client.tree.sync()
	client.tree.copy_global_to(guild=guild)
	await client.tree.sync(guild=guild)

	if auction_watcher_task is None or auction_watcher_task.done():
		auction_watcher_task = asyncio.create_task(watch_expired_auctions())

@client.event
async def on_message(message):
	for handler in on_message_handlers:
		r = await handler(message)
		if r == True: # return True to signal message capture
			return

def load_module_descriptor(module, descriptor):
	if "type" not in descriptor:
		print("MISSING module.type ATTRIBUTE IN %s" % str(module));
		return

	type = descriptor["type"].lower()
	match type:
		case "command":
			if ("name" not in descriptor) or ("callback" not in descriptor):
				print("MISSING module.name OR module.callback ATTRIBUTE IN %s" % str(module));
				return
			name = descriptor["name"]
			callback = descriptor["callback"]
			description = descriptor["description"] if ("description" in descriptor) else "..."
			nsfw = bool(descriptor["nsfw"]) if ("nsfw" in descriptor) else False
			print("registerd /%s" % name)
			client.tree.add_command(app_commands.Command(name=name, description=description, callback=callback, nsfw=nsfw))
			return

		case "context_menu" | "contextmenu":
			if ("name" not in descriptor) or ("callback" not in descriptor):
				print("MISSING module.name OR module.callback ATTRIBUTE IN %s" % str(module));
				return
			name = descriptor["name"]
			callback = descriptor["callback"]
			nsfw = bool(descriptor["nsfw"]) if ("nsfw" in descriptor) else False
			print("registerd /%s" % name)
			client.tree.add_command(app_commands.ContextMenu(name=name, callback=callback, nsfw=nsfw))
			return

		case "onmessage" | "on_message" | "messagehandler" | "message_handler" | "message":
			if "callback" not in descriptor:
				print("MISSING module.callback ATTRIBUTE IN %s" % str(module));
				return
			on_message_handlers.append(descriptor["callback"])
			return

def load_module(module):
	if hasattr(module, "modules"):
		for descriptor in module.modules:
			load_module_descriptor(module, descriptor);

	if not hasattr(module, "module"):
		return # no longer required

	if "type" not in module.module:
		print("MISSING module.type ATTRIBUTE IN %s" % str(module));
		return

	load_module_descriptor(module, module.module);

client.run(env.BOT_TOKEN)
