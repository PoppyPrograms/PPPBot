from random import choice

import discord

from storage import (
    play_gamble,
    read_balances as read_balances_from_storage,
    read_gamble_stats as read_gamble_stats_from_storage,
    reserve_wager as reserve_wager_in_storage,
    settle_wager as settle_wager_in_storage,
    write_balances as write_balances_to_storage,
    write_gamble_stats as write_gamble_stats_to_storage,
)


def read_balances():
    return read_balances_from_storage()


def write_balances(balances):
    write_balances_to_storage(balances)


def read_gamble_stats():
    return read_gamble_stats_from_storage()


def write_gamble_stats(stats):
    write_gamble_stats_to_storage(stats)


def record_gamble_result(stats, user_id, amount, won):
    gains, losses = stats.get(user_id, (0, 0))
    if won:
        gains += amount
    else:
        losses += amount
    stats[user_id] = (gains, losses)


def reserve_wager(user_id, amount):
    return reserve_wager_in_storage(user_id, amount)


def settle_wager(user_id, amount, outcome):
    return settle_wager_in_storage(user_id, amount, outcome)


async def gamble(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The gamble amount must be greater than zero.", ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    won = choice((True, False))
    played, new_balance = play_gamble(user_id, amount, won)
    if not played:
        await interaction.response.send_message(
            f"You only have {new_balance} burgas, so you cannot gamble {amount} <:rage:1348642100916387891>",
            ephemeral=True,
        )
        return

    if won:
        result = f"You won {amount} burgas <:tony:1450129761916551188>"
    else:
        result = f"You lost {amount} burgas <:good:1364955467016831056>"

    await interaction.response.send_message(
        f"{result} Your balance is now {new_balance} burgas <:indiar:1396971369220276365>"
    )


module = {
    "type": "command",
    "name": "gamble",
    "description": "Gamble burgas on a 50/50 coin flip",
    "callback": gamble,
}
