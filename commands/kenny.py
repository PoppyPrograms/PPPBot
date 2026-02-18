from datetime import timedelta
from random import randrange

import discord

# TODO use actual jail whenever lemon DB comes out and refactor this piece of trash

kenny_id = 1276528572898611271
hell_channel_id = 1473803213672288337
kenny = None
hell_channel = None


async def find_kenny(interaction: discord.Interaction):
    global kenny, hell_channel
    if kenny is None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "i cant get the guild <:guhhhh:1318198344258027540>"
            )
            return None
        kenny = guild.get_member(kenny_id)
        hell_channel = guild.get_channel(hell_channel_id)

    return kenny


def easeInQuad(t):
    return ((t * t) / 10000) * 24 * 3


async def kenny_command(interaction: discord.Interaction):

    kenny = await find_kenny(interaction)
    if kenny is None:
        await interaction.response.send_message(
            "Could not find kenny what the fuck <:WHYYYY:1171546567614926949>"
        )
        return
    timeoutDuration = easeInQuad(randrange(1, 101))
    await kenny.timeout(timedelta(hours=timeoutDuration))
    if hell_channel is not None:
        await hell_channel.send(
            "<@"
            + str(kenny_id)
            + "> you have been jailed for "
            + str(timeoutDuration)
            + " hours"
        )  # i hate pep8
    else:
        await interaction.response.send_message(
            "i coudnt send them a message <:WHYYYY:1171546567614926949>"
        )


module = {
    "type": "command",
    "name": "kenny",
    "description": "Puts kenny in jail for a random amount of time",
    "callback": kenny_command,
}
