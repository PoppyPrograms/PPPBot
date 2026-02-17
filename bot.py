import discord, glob, env
from discord.ext import commands
from discord import app_commands
import helpers

modules = []
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

def load_module(module):
	if not hasattr(module, "module"):
		print("MISSING module ATTRIBUTE IN %s" % str(module));
		return

	if "type" not in module.module:
		print("MISSING module.type ATTRIBUTE IN %s" % str(module));
		return

	descriptor = module.module
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

client.run(env.BOT_TOKEN)
