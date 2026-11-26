"""Commands for rolling and collecting reggies."""

from random import randint

import discord

from storage import capture_reggie, get_reggies


REGGIE_MIN_ROLL = 250
REGGIE_MAX_ROLL = 300
ROLL_MIN = 1
ROLL_MAX = 1000
DISPLAY_LIMIT = 20


async def reggie(interaction: discord.Interaction):
    """Roll a number and capture a reggie when it lands in range."""
    roll = randint(ROLL_MIN, ROLL_MAX)
    if REGGIE_MIN_ROLL <= roll <= REGGIE_MAX_ROLL:
        capture_reggie(interaction.user.id, roll)
        collection = get_reggies(interaction.user.id)
        await interaction.response.send_message(
            f"🎲 You rolled **{roll}** and caught a reggie! "
            f"You now have **{len(collection)}** "
            f"reggie{'s' if len(collection) != 1 else ''}. "
            f"Use `/reggies` to see your collection."
        )
        return

    await interaction.response.send_message(
        f"🎲 You rolled **{roll}**. No reggie this time; "
        f"you need a number from {REGGIE_MIN_ROLL} to {REGGIE_MAX_ROLL}."
    )


async def reggies(
    interaction: discord.Interaction,
    user: discord.User = None,
):
    """Show a user's captured reggies."""
    owner = user or interaction.user
    collection = get_reggies(owner.id)
    if not collection:
        await interaction.response.send_message(
            f"{owner.mention} has not caught any reggies yet. Try `/reggie`!",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    recent = collection[:DISPLAY_LIMIT]
    lines = [
        f"• Reggie #{entry['id']} (roll **{entry['roll']}**)"
        for entry in recent
    ]
    if len(collection) > DISPLAY_LIMIT:
        lines.append(f"…and {len(collection) - DISPLAY_LIMIT} more.")

    embed = discord.Embed(
        title=f"{owner.display_name}'s reggies ({len(collection)})",
        description="\n".join(lines),
        colour=discord.Colour.default(),
    )
    await interaction.response.send_message(embed=embed)


modules = [
    {
        "type": "command",
        "name": "reggie",
        "description": "Roll a number for a chance to catch a reggie",
        "callback": reggie,
    },
    {
        "type": "command",
        "name": "reggies",
        "description": "View your or another user's reggie collection",
        "callback": reggies,
    },
]
