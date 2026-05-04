import discord

async def burgaleaderborad(interaction: discord.Interaction):
    burgas = []
    client = interaction.client
    with open("burga.csv") as file:
        for line in file.readlines():
            split = line.split(",")
            user = await client.fetch_user(split[0])
            print(user)
            nickname = user.display_name
            burgas.append([int(split[1]), nickname])
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
