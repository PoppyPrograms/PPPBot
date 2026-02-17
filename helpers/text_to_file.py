from io import BytesIO
import discord

def text_to_file(contents: str, filename="file.txt"):
	bytes = BytesIO(contents.encode("utf-8"))
	return discord.File(fp=bytes, filename=filename)
