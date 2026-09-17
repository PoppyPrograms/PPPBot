import random

import discord

from storage import adjust_balance, steal_burga


BURGA_MILESTONES = (10, 100, 1000)
REPEATING_MILESTONE = 1000
BELLYACHE_INTERVAL = 5
UNLUCKY_LOSS_CHANCE = 0.10
QUEEN_DOUBLE_CHANCE = 0.25

UNLUCKY_USER_ID = "1550197457756102728"
BELLYACHE_USER_ID = "275991832524095489"
BURGA_THIEF_USER_ID = "1451180336397418528"
BURGA_QUEEN_USER_ID = "128238157761216512"


def is_big_milestone(count):
    return count in BURGA_MILESTONES or (
        count > BURGA_MILESTONES[-1] and count % REPEATING_MILESTONE == 0
    )


def is_bellyache_milestone(count):
    return count > 0 and count % BELLYACHE_INTERVAL == 0


def target_name(target):
    return getattr(target, "display_name", str(target))


async def eatburga(
    interaction: discord.Interaction,
    target: discord.Member = None,
):
    user_id = str(interaction.user.id)

    if target is not None:
        if user_id != BURGA_THIEF_USER_ID:
            await interaction.response.send_message(
                "Only the designated burga thief can steal from a target "
                "<:killsyou:1511341401277989005>",
                ephemeral=True,
            )
            return
        if target.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot steal from yourself <:killsyou:1511341401277989005>",
                ephemeral=True,
            )
            return
        if target.bot:
            await interaction.response.send_message(
                "You cannot steal from a bot <:killsyou:1511341401277989005>",
                ephemeral=True,
            )
            return

        result = steal_burga(user_id, target.id)
        if not result["stolen"]:
            if result["reason"] == "daily_limit":
                message = (
                    "You have already used today's burga theft. Try again tomorrow "
                    "<:goon:1505288457017229312>"
                )
            else:
                message = (
                    f"{target_name(target)} has no available burgas to steal "
                    "<:WHYYYY:1171546567614926949>"
                )
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.send_message(
            f"<:indiar:1396971369220276365> You stole 1 burga from "
            f"{target_name(target)}. You now have {result['thief_balance']} burgas.",
            ephemeral=True,
        )
        return

    amount = 1
    if (
        user_id == BURGA_QUEEN_USER_ID
        and random.random() < QUEEN_DOUBLE_CHANCE
    ):
        amount = 2

    user_burga_count = adjust_balance(user_id, amount)
    if (
        user_id == UNLUCKY_USER_ID
        and random.random() < UNLUCKY_LOSS_CHANCE
    ):
        user_burga_count = adjust_balance(user_id, -1)

    private_messages = [
        f"<:burga:1488480983517892800> logged. You have eaten "
        f"{user_burga_count} burgas now"
    ]
    public_messages = []
    if is_big_milestone(user_burga_count):
        public_messages.append(
            f"<:burga:1488480983517892800> <@{user_id}> reached "
            f"{user_burga_count} burgas!"
        )
    if user_id == BELLYACHE_USER_ID and is_bellyache_milestone(
        user_burga_count
    ):
        private_messages.append(
            f"<:WHYYYY:1171546567614926949> You've eaten {user_burga_count} "
            "burgas. Keep going and you'll get a bellyache!"
        )

    await interaction.response.send_message(
        "\n".join(private_messages),
        ephemeral=True,
    )
    if public_messages:
        await interaction.followup.send(
            "\n".join(public_messages),
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


module = {
	"type": "command",
	"name": "eatburga",
	"description": "Logs a burga eaten",
	"callback": eatburga,
}
