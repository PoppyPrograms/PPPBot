from discord import Webhook
import aiohttp
import env

async def send_webhook_message(content, *args, **kwargs):
	async with aiohttp.ClientSession() as session:
		webhook = Webhook.from_url(env.WEBHOOK_URL, session=session)
		await webhook.send(content, *args, **kwargs)
