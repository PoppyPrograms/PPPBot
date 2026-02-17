import discord

async def roadrunner(interaction: discord.Interaction):
	await interaction.response.send_message("<:road:1459339557529980958>")


module = {
	"type": "command",
	"name": "roadrunner",
	"description": "sends a little roadrunner",
	"callback": roadrunner
}
