from discord import Webhook
import aiohttp
import env

async def send_webhook_message(content, *args, **kwargs):
	session = aiohttp.ClientSession()
	webhook = Webhook.from_url(env.WEBHOOK_URL, session=session)
	await webhook.send(content, *args, **kwargs)
	await session.close()
