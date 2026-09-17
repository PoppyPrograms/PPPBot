import discord

from storage import read_balances


async def burgaleaderborad(interaction: discord.Interaction):
    burgas = []
    client = interaction.client
    for user_id, amount in read_balances().items():
        user = await client.fetch_user(int(user_id))
        nickname = user.display_name
        burgas.append([amount, nickname])
    burgas.sort()

    description = "\n".join([f"{burga[1]}: {burga[0]} burgas" for burga in burgas[::-1]])
    embed = discord.Embed( title="Burga Leaderboard", colour=discord.Colour.default(), description=description)
    embed.set_footer(text="Use /eatburga to log a burger")
    await interaction.response.send_message(embed=embed)
module = {
	"type": "command",
	"name": "burgerleaderboard",
	"description": "Returns the burga leaderboard",
	"callback": burgaleaderborad
}
