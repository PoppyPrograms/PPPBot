import discord


async def error_test(interaction: discord.Interaction):
    """Trigger a deliberate failure to verify production error reporting."""

    permissions = getattr(interaction.user, "guild_permissions", None)
    if permissions is None or not permissions.administrator:
        await interaction.response.send_message(
            "Only server administrators can run this test.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Triggering an intentional error; check the logs channel.", ephemeral=True
    )
    raise RuntimeError("Intentional test error from /error_test")


module = {
    "type": "command",
    "name": "error_test",
    "description": "Trigger an intentional error for log testing",
    "callback": error_test,
}
