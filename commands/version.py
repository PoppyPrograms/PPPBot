import discord
import os

async def version(interaction: discord.Interaction, content: str):
    await interaction.response.send_message(f"Version "+os.getenv("BOT_VERSION"))
module = {
	"type": "command",
	"name": "version",
	"description": "gives the version of the bot to see if my cd is dogshit or not",
	"callback": version
}
