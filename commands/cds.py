import discord
import helpers

# these are probably really bad ideas but as the framework design architect i guess i should make a command to demonstrate the CDS system

def cds_user_index_add(filename: str):
	list = helpers.storage_download("USERDATA-index.lst")
	if list == False: # hm...
		helpers.storage_upload("USERDATA-index.lst", filename.encode("utf-8"))
		return
	list = list.decode("utf-8")
	if filename in list.split(","):
		return
	list = list + "," + filename
	helpers.storage_upload("USERDATA-index.lst", list.encode("utf-8"))

async def cds_download_command(interaction: discord.Interaction, filename: str):
	# if you just let people upload and download any arbitrary file that would be a disaster
	download = helpers.storage_download("USERDATA_" + filename)
	if download == False:
		await interaction.response.send_message("Could not find file on server.", ephemeral=True)
		return

	download_as_string = download.decode("utf-8") # normally this is bytearray (cuz binary data)
	file = helpers.text_to_file(download_as_string, filename=filename)
	await interaction.response.send_message(file=file, ephemeral=True)

async def cds_upload_command(interaction: discord.Interaction, filename: str, content: str):
	content_as_bytes = content.encode("utf-8") # same thing as download_as_string in reverse
	if len(content_as_bytes) > 256: # length limit so you dont blow up toto's computer
		await interaction.response.send_message("Too long!", ephemeral=True)
		return

	if "," in filename:
		await interaction.response.send_message("Disallowed character", ephemeral=True)
		return

	upload = helpers.storage_upload("USERDATA_" + filename, content_as_bytes)
	if upload == False:
		await interaction.response.send_message("Could not upload file to server.", ephemeral=True)
		return

	cds_user_index_add(filename) # add this to the index
	await interaction.response.send_message("Success!", ephemeral=True)

async def cds_list_command(interaction: discord.Interaction):
	download = helpers.storage_download("USERDATA-index.lst")
	if download == False:
		await interaction.response.send_message("Index error.", ephemeral=True)
		return
	list = download.decode("utf-8")
	list = ", ".join(list.split(","))
	file = helpers.text_to_file(list, filename="index.lst.txt")
	await interaction.response.send_message(file=file, ephemeral=True)

modules = [{
	"type": "command",
	"name": "cds_download",
	"description": "Download from CDS server",
	"callback": cds_download_command
}, {
	"type": "command",
	"name": "cds_upload",
	"description": "Upload to CDS server",
	"callback": cds_upload_command
}, {
	"type": "command",
	"name": "cds_list",
	"description": "List user files on CDS server",
	"callback": cds_list_command
}]
