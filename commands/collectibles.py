import json

import discord

from storage import (
    StorageError,
    buy_listing,
    cancel_listing,
    claim_collectible,
    close_expired_auctions,
    create_listing,
    get_collection,
    get_item,
    get_market_listings,
    place_bid,
    transfer_collectible,
)


PAGE_LENGTH = 3800
ALLOWED_MENTIONS = discord.AllowedMentions.none()


def guild_id_for(interaction):
    return str(interaction.guild.id) if interaction.guild is not None else None


def channel_id_for(interaction):
    return str(interaction.channel_id)


def mention(user_id):
    return f"<@{user_id}>"


def one_line(value, limit=140):
    value = " ".join((value or "").split())
    if not value:
        return "(attachment-only message)"
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def truncate(value, limit):
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def json_list(value):
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return []
    return result if isinstance(result, list) else []


def chunks(lines):
    pages = []
    current = []
    current_length = 0

    for line in lines:
        line_length = len(line) + (1 if current else 0)
        if current and current_length + line_length > PAGE_LENGTH:
            pages.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length

    if current:
        pages.append("\n".join(current))
    return pages


async def send_error(interaction, error):
    await interaction.response.send_message(f"❌ {error}", ephemeral=True)


async def send_pages(interaction, title, pages):
    embeds = [
        discord.Embed(
            title=title,
            description=page,
            colour=discord.Colour.default(),
        )
        for page in pages
    ]
    await interaction.response.send_message(
        embed=embeds[0], allowed_mentions=ALLOWED_MENTIONS
    )
    for embed in embeds[1:]:
        await interaction.followup.send(
            embed=embed, allowed_mentions=ALLOWED_MENTIONS
        )


async def ensure_guild(interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Collectibles only work inside a server.", ephemeral=True
        )
        return None
    return guild_id_for(interaction)


def embed_snapshot(message):
    snapshots = []
    for embed in message.embeds[:3]:
        snapshots.append(
            {
                "title": embed.title or "",
                "description": embed.description or "",
                "url": embed.url or "",
            }
        )
    return snapshots


async def claim_message(interaction: discord.Interaction, message: discord.Message):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    if message.author.bot:
        await interaction.response.send_message(
            "Bot messages cannot become collectibles <:puncher:1511285878427877446>", ephemeral=True
        )
        return
    if message.author.id == interaction.user.id:
        await interaction.response.send_message(
            "You cannot claim your own message <:killsyou:1511341401277989005>", ephemeral=True
        )
        return
    if not (message.content or "").strip() and not message.attachments and not message.embeds:
        await interaction.response.send_message(
            "That message has nothing collectible in it <:spun:1375397620339576913>", ephemeral=True
        )
        return

    try:
        item, created = claim_collectible(
            guild_id=guild_id,
            message_id=message.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            content=message.content or "",
            attachment_urls=[attachment.url for attachment in message.attachments],
            embed_data=embed_snapshot(message),
            message_url=message.jump_url,
            sent_at=int(message.created_at.timestamp()),
            owner_id=interaction.user.id,
        )
    except StorageError as error:
        await send_error(interaction, error)
        return
    if not created:
        await interaction.response.send_message(
            f"That message is already collectible #{item['id']}, owned by "
            f"{mention(item['owner_id'])} <:indiar:1396971369220276365>",
            ephemeral=True,
            allowed_mentions=ALLOWED_MENTIONS,
        )
        return

    await interaction.response.send_message(
        f"🎴 You claimed collectible #{item['id']} from {mention(item['author_id'])} <:durr:1500988411291369613> "
        "Use `/collection` to see it.",
        allowed_mentions=ALLOWED_MENTIONS,
    )


async def collection(interaction: discord.Interaction, user: discord.Member = None):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    owner = user or interaction.user
    items = get_collection(guild_id, owner.id)
    if not items:
        await interaction.response.send_message(
            f"{mention(owner.id)} has no collectibles yet <:WHYYYY:1171546567614926949>",
            ephemeral=True,
            allowed_mentions=ALLOWED_MENTIONS,
        )
        return

    lines = []
    for item in items:
        lines.append(
            f"`#{item['id']}` {one_line(item['content'])} "
            f"— from {mention(item['author_id'])} ([source]({item['message_url']}))"
        )
    await send_pages(interaction, f"{owner.display_name}'s collection", chunks(lines))


async def item(interaction: discord.Interaction, item_id: int):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    collectible = get_item(item_id, guild_id)
    if collectible is None:
        await send_error(interaction, f"Collectible #{item_id} does not exist here <:WHYYYY:1171546567614926949>")
        return

    content = collectible["content"] or "*(attachment-only message)*"
    embed_kwargs = {
        "title": f"Collectible #{collectible['id']}",
        "description": truncate(content, 3900),
        "colour": discord.Colour.default(),
    }
    if collectible["message_url"]:
        embed_kwargs["url"] = collectible["message_url"]
    embed = discord.Embed(**embed_kwargs)
    embed.add_field(
        name="Original creator",
        value=mention(collectible["author_id"]),
        inline=True,
    )
    embed.add_field(
        name="Current owner",
        value=mention(collectible["owner_id"]),
        inline=True,
    )
    if collectible["message_url"]:
        embed.add_field(
            name="Source",
            value=f"[Jump to original message]({collectible['message_url']})",
            inline=False,
        )

    attachments = json_list(collectible["attachment_urls"])
    if attachments:
        attachment_text = "\n".join(
            f"[Attachment {index}]({url})"
            for index, url in enumerate(attachments, start=1)
        )
        embed.add_field(
            name="Attachments",
            value=truncate(attachment_text, 1024),
            inline=False,
        )

    await interaction.response.send_message(
        embed=embed, allowed_mentions=ALLOWED_MENTIONS
    )


async def market(interaction: discord.Interaction):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    close_expired_auctions()
    listings = get_market_listings(guild_id)
    if not listings:
        await interaction.response.send_message(
            "The collectible market is empty <:frnch:1396370424056778904>", ephemeral=True
        )
        return

    lines = []
    for listing in listings:
        snippet = one_line(listing["content"], 100)
        if listing["kind"] == "sale":
            target = (
                f" reserved for {mention(listing['target_buyer_id'])}"
                if listing["target_buyer_id"]
                else ""
            )
            lines.append(
                f"`#{listing['id']}` sale — item `#{listing['item_id']}` — "
                f"{listing['price']} burgas{target} — {snippet}"
            )
        else:
            highest = listing["highest_bid"] or listing["price"]
            lines.append(
                f"`#{listing['id']}` auction — item `#{listing['item_id']}` — "
                f"current {highest} burgas — ends <t:{listing['ends_at']}:R> — {snippet}"
            )
    await send_pages(interaction, "Collectible market", chunks(lines))


async def give(
    interaction: discord.Interaction,
    item_id: int,
    recipient: discord.Member,
    price: int = 0,
):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    if recipient.bot:
        await send_error(interaction, "Bots cannot own collectibles <:killsyou:1511341401277989005>")
        return
    try:
        transfer_collectible(
            guild_id, item_id, interaction.user.id, recipient.id, price
        )
    except StorageError as error:
        await send_error(interaction, error)
        return

    action = "gave away" if price == 0 else f"sold for {price} burgas to"
    await interaction.response.send_message(
        f"You {action} {mention(recipient.id)} collectible #{item_id} <:spun:1375397620339576913>",
        allowed_mentions=ALLOWED_MENTIONS,
    )


async def sell(
    interaction: discord.Interaction,
    item_id: int,
    price: int,
    buyer: discord.Member = None,
):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    if buyer is not None and buyer.bot:
        await send_error(interaction, "Bots cannot buy collectibles.")
        return
    if buyer is not None and buyer.id == interaction.user.id:
        await send_error(interaction, "You cannot sell to yourself.")
        return
    try:
        listing = create_listing(
            guild_id=guild_id,
            item_id=item_id,
            channel_id=channel_id_for(interaction),
            seller_id=interaction.user.id,
            kind="sale",
            price=price,
            target_buyer_id=buyer.id if buyer is not None else None,
        )
    except StorageError as error:
        await send_error(interaction, error)
        return

    target = f" for {mention(buyer.id)}" if buyer is not None else ""
    await interaction.response.send_message(
        f"Listed collectible #{item_id} as sale #{listing['id']} for "
        f"{price} burgas{target}. Use `/buy {listing['id']}` to purchase it <:bliss:1375397433546244219>",
        allowed_mentions=ALLOWED_MENTIONS,
    )


async def buy(interaction: discord.Interaction, listing_id: int):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    close_expired_auctions()
    try:
        listing = buy_listing(guild_id, listing_id, interaction.user.id)
    except StorageError as error:
        await send_error(interaction, error)
        return

    await interaction.response.send_message(
        f"You bought collectible #{listing['item_id']} for "
        f"{listing['price']} burgas <:good:1364955467016831056>",
    )


async def auction(
    interaction: discord.Interaction,
    item_id: int,
    starting_price: int,
    duration_minutes: int,
):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    if duration_minutes > 7 * 24 * 60:
        await send_error(interaction, "Auctions can last at most seven days.")
        return
    try:
        listing = create_listing(
            guild_id=guild_id,
            item_id=item_id,
            channel_id=channel_id_for(interaction),
            seller_id=interaction.user.id,
            kind="auction",
            price=starting_price,
            duration_minutes=duration_minutes,
        )
    except StorageError as error:
        await send_error(interaction, error)
        return

    await interaction.response.send_message(
        f"Auction #{listing['id']} started for collectible #{item_id}. "
        f"Starting bid: {starting_price} burgas; ends <t:{listing['ends_at']}:R> <:burga:1493907112542077092>",
    )


async def bid(interaction: discord.Interaction, listing_id: int, amount: int):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    close_expired_auctions()
    try:
        listing = place_bid(guild_id, listing_id, interaction.user.id, amount)
    except StorageError as error:
        await send_error(interaction, error)
        return

    await interaction.response.send_message(
        f"Bid accepted: {amount} burgas on auction #{listing_id} <:burga:1493907112542077092> "
        f"Use `/market` to watch it.",
    )


async def cancel(interaction: discord.Interaction, listing_id: int):
    guild_id = await ensure_guild(interaction)
    if guild_id is None:
        return
    try:
        listing = cancel_listing(guild_id, listing_id, interaction.user.id)
    except StorageError as error:
        await send_error(interaction, error)
        return

    await interaction.response.send_message(
        f"Listing #{listing_id} cancelled; collectible #{listing['item_id']} is back in your collection <:goon:1505288457017229312>"
    )


modules = [
    {
        "type": "context_menu",
        "name": "Claim message",
        "callback": claim_message,
    },
    {
        "type": "command",
        "name": "collection",
        "description": "View a member's collectible messages",
        "callback": collection,
    },
    {
        "type": "command",
        "name": "item",
        "description": "View a collectible message",
        "callback": item,
    },
    {
        "type": "command",
        "name": "market",
        "description": "Browse collectible messages for sale",
        "callback": market,
    },
    {
        "type": "command",
        "name": "give",
        "description": "Give or sell a collectible directly",
        "callback": give,
    },
    {
        "type": "command",
        "name": "sell",
        "description": "List a collectible for a fixed price",
        "callback": sell,
    },
    {
        "type": "command",
        "name": "buy",
        "description": "Buy a collectible listing",
        "callback": buy,
    },
    {
        "type": "command",
        "name": "auction",
        "description": "Start an auction for a collectible",
        "callback": auction,
    },
    {
        "type": "command",
        "name": "bid",
        "description": "Bid on a collectible auction",
        "callback": bid,
    },
    {
        "type": "command",
        "name": "cancel_listing",
        "description": "Cancel your active collectible listing",
        "callback": cancel,
    },
]
