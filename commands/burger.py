import discord

async def eatburga(interaction: discord.Interaction):
	id = interaction.user.id
	burgas = {}
	with open("burga.csv") as file:
		for line in file.readlines():
			split = line.split(",")
			print(split, id)
			burgas[split[0]] = int(split[1])

	if str(id) in burgas:
		burgas[str(id)] += 1
	else:
		burgas[str(id)] = 1
	with open("burga.csv", "w") as file:
		file.write("\n".join([f"{key},{value}" for key, value in burgas.items()]))
	user_burga_count = burgas[str(id)]

	await interaction.response.send_message(f"<:burga:1488480983517892800> logged. You have eaten {user_burga_count} burgas now")
module = {
	"type": "command",
	"name": "eatburga",
	"description": "Logs a burga eaten",
	"callback": eatburga
}