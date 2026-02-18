import discord
import helpers

async def webhook_command(interaction: discord.Interaction, content: str, username: str, avatar_url: str):
	try:
		await helpers.send_webhook_message(content, username=username, avatar_url=avatar_url)
		await interaction.response.send_message("Sucess!", ephemeral=True)
	except Exception as e:
		print(e)
		await interaction.response.send_message("An unknown error occured.", ephemeral=True)

module = {
	"type": "command",
	"name": "webhook_test",
	"description": "Webhook Test",
	"callback": webhook_command
}
