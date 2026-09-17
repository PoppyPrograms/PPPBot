# Kamchatka deployment

GitHub Actions builds `ghcr.io/poppyprograms/pppbot:main` after each push to
`main`. A systemd timer on Kamchatka pulls that tag every five minutes and runs
the service with Docker Compose.

The host must contain `/etc/pppbot/pppbot.env`, readable only by root, with:

```dotenv
DISCORD_TOKEN=...
GUILD_ID=...
WEBHOOK_URL=...
LOGS_CHANNEL_WEBHOOK_URL=...
```

`LOGS_CHANNEL_WEBHOOK_URL` is the Discord webhook used for redacted error
reports from event handlers, commands, background tasks, and startup/thread
failures. It is optional; Docker logs remain the fallback when it is omitted.

If the GHCR package is private, log Docker into `ghcr.io` as root using a token
with only `read:packages` access. The deployed files are:

- `/opt/pppbot/compose.yaml`
- `/etc/systemd/system/pppbot-update.service`
- `/etc/systemd/system/pppbot-update.timer`

Enable deployment with:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now pppbot-update.timer
sudo systemctl start pppbot-update.service
```

Inspect it with `docker logs pppbot` and
`systemctl status pppbot-update.service`.
