import discord

from storage import adjust_balance


async def eatburga(interaction: discord.Interaction):
    user_burga_count = adjust_balance(str(interaction.user.id), 1)

    await interaction.response.send_message(f"<:burga:1488480983517892800> logged. You have eaten {user_burga_count} burgas now")
module = {
	"type": "command",
	"name": "eatburga",
	"description": "Logs a burga eaten",
	"callback": eatburga
}
