from pathlib import Path
from random import choice

import discord


BURGA_FILE = Path("burga.csv")


def read_balances():
    BURGA_FILE.touch(exist_ok=True)
    balances = {}

    with BURGA_FILE.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            user_id, count = line.split(",", 1)
            balances[user_id] = int(count)

    return balances


def write_balances(balances):
    contents = "\n".join(
        f"{user_id},{count}" for user_id, count in balances.items()
    )
    BURGA_FILE.write_text(contents, encoding="utf-8")


async def gamble(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The gamble amount must be greater than zero.", ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    balances = read_balances()
    balance = balances.get(user_id, 0)

    if amount > balance:
        await interaction.response.send_message(
            f"You only have {balance} burgas, so you cannot gamble {amount} <:rage:1348642100916387891>",
            ephemeral=True,
        )
        return

    won = choice((True, False))
    new_balance = balance + amount if won else balance - amount
    balances[user_id] = new_balance
    write_balances(balances)

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
