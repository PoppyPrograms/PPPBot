import discord

async def airunner(interaction: discord.Interaction, content: str):
    # TODO: Add ID to .env. Toto can u do it im busy :appl:
    await interaction.response.send_message(f"<@{275991832524095489}> {content}")
module = {
	"type": "command",
	"name": "airunner",
	"description": "Ask the superior AI",
	"callback": airunner
}
