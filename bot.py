import discord
import glob
import env
from discord.ext import commands
from discord import app_commands

modules = []
on_message_handlers = []
for m in glob.glob("commands/*.py"):
	module = __import__(m[:-3].replace("/","."), globals(), locals(), [], 0)
	modules.append(getattr(module, m[9:-3]))

guild=discord.Object(id=env.GUILD_ID)
intents = discord.Intents.all()
client = commands.Bot(command_prefix="&", intents=intents)

@client.event
async def on_ready():
	client.tree.clear_commands(guild=guild)
	await client.tree.sync()

	for module in modules:
		load_module(module)

	client.tree.copy_global_to(guild=guild)
	await client.tree.sync(guild=guild)

@client.event
async def on_message(message):
	for handler in on_message_handlers:
		r = await handler(message)
		if (r == True): # return True to signal message capture
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
			client.tree.add_command(app_commands.Command(name=name, description=description, callback=callback, nsfw=nsfw))
			return

		case "context_menu" | "contextmenu":
			if ("name" not in descriptor) or ("callback" not in descriptor):
				print("MISSING module.name OR module.callback ATTRIBUTE IN %s" % str(module));
				return
			name = descriptor["name"]
			callback = descriptor["callback"]
			nsfw = bool(descriptor["nsfw"]) if ("nsfw" in descriptor) else False
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
