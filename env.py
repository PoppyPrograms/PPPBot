import os

CDS_SERVER_HOST = "127.0.0.1"
CDS_SERVER_HOSTNAME = "qcds.totocodes.fr"
CDS_SERVER_PORT = 7345
CDS_CERT_PATH = "ssl/cert.pem"
CDS_TOKEN = bytes.fromhex(os.environ["CDS_AUTH_TOKEN"])

if "PPPBOT_CDS_ONLY" not in os.environ:
	BOT_TOKEN = os.environ["DISCORD_TOKEN"]
	GUILD_ID = os.environ["GUILD_ID"]
	WEBHOOK_URL = os.environ["WEBHOOK_URL"]
