import discord

from commands.gamble import read_gamble_stats


LEADERBOARD_DESCRIPTION_LIMIT = 3900


async def get_display_name(interaction, user_id):
    try:
        numeric_user_id = int(user_id)
    except ValueError:
        return f"User {user_id}"

    user = None
    guild = getattr(interaction, "guild", None)
    if guild is not None:
        user = guild.get_member(numeric_user_id)

    if user is None:
        try:
            user = await interaction.client.fetch_user(numeric_user_id)
        except (discord.DiscordException, ValueError):
            return f"User {user_id}"

    name = user.display_name.replace("\r", " ").replace("\n", " ")
    name = discord.utils.escape_markdown(name)
    return discord.utils.escape_mentions(name)


def split_leaderboard_lines(lines):
    chunks = []
    current = []
    current_length = 0

    for line in lines:
        line_length = len(line) + (1 if current else 0)
        if current and current_length + line_length > LEADERBOARD_DESCRIPTION_LIMIT:
            chunks.append("\n".join(current))
            current = []
            current_length = 0

        current.append(line)
        current_length += len(line) + (1 if len(current) > 1 else 0)

    if current:
        chunks.append("\n".join(current))

    return chunks


async def gamble_leaderboard(interaction: discord.Interaction):
    stats = read_gamble_stats()
    entries = []

    for user_id, (gains, losses) in stats.items():
        entries.append(
            {
                "name": await get_display_name(interaction, user_id),
                "gains": gains,
                "losses": losses,
                "net": gains - losses,
            }
        )

    entries.sort(
        key=lambda entry: (entry["net"], entry["gains"], entry["losses"]),
        reverse=True,
    )

    if not entries:
        embed = discord.Embed(
            title="Gambling Leaderboard",
            description="No gambling results yet </3",
            colour=discord.Colour.default(),
        )
        embed.set_footer(text="Use /gamble to place a bet")
        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )
        return

    lines = [
        f"`{position:>2}.` {entry['name']} — "
        f"gained {entry['gains']} | lost {entry['losses']} | "
        f"net {entry['net']:+d}"
        for position, entry in enumerate(entries, start=1)
    ]

    embeds = []
    for chunk in split_leaderboard_lines(lines):
        embed = discord.Embed(
            title="Gambling Leaderboard",
            description=chunk,
            colour=discord.Colour.default(),
        )
        embed.set_footer(text="Use /gamble to place a bet")
        embeds.append(embed)

    allowed_mentions = discord.AllowedMentions.none()
    await interaction.response.send_message(
        embed=embeds[0], allowed_mentions=allowed_mentions
    )
    for embed in embeds[1:]:
        await interaction.followup.send(
            embed=embed, allowed_mentions=allowed_mentions
        )


module = {
    "type": "command",
    "name": "gambleleaderboard",
    "description": "Shows everyone's gambling gains and losses",
    "callback": gamble_leaderboard,
}
