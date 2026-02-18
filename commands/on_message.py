import discord

async def my_message_handler(message) -> bool:
	if (message.content.startswith("<PPPBOT_TEST_MESSAGE_SIGNATURE#d5f706d603d68c0486986535b7b95c5a>")):
		await message.channel.send("Hello!");
	# True == "consumed" message, i.e: stop handling
	# False == continue calling other handlers
	return False

async def my_other_message_handler(message) -> bool:
	if (message.content.startswith("<PPPBOT_TEST_MESSAGE_SIGNATURE_2#4bce4d8f1dd3ad4812b8c9aa70ae4756>")):
		await message.channel.send("Hello again!");
	return False

modules = [
	{	"type": "message_handler",
		"callback": my_message_handler },

	{	"type": "message_handler",
		"callback": my_other_message_handler },
]
