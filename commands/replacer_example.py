import discord
import helpers

async def my_message_handler(message) -> bool:
	if (message.content.startswith("<PPPBOT_TEST_MESSAGE_SIGNATURE_3#72d4335b306fe2ea75734f367a4304d3>")):
		content = "fake message example"
		username = message.author.display_name
		avatar_url = message.author.display_avatar.url
		await helpers.send_webhook_message(content, username=username, avatar_url=avatar_url) # send our epic updated / mangled / parsed / replaced message
		await message.delete()
		return True
	return False

module = {
	"type": "message_handler",
	"callback": my_message_handler
}
