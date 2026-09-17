from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


DATA_DIRECTORY = Path(__file__).resolve().parent
DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
DATABASE_FILE = DATA_DIRECTORY / "pppbot.sqlite3"
LEGACY_BALANCE_FILE = DATA_DIRECTORY / "burga.csv"
LEGACY_GAMBLE_STATS_FILE = DATA_DIRECTORY / "gamble_stats.csv"


class StorageError(Exception):
    """Base class for expected economy and marketplace errors."""


class NotFoundError(StorageError):
    pass


class NotOwnerError(StorageError):
    pass


class ConflictError(StorageError):
    pass


class InvalidActionError(StorageError):
    pass


class InsufficientFundsError(StorageError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS balances (
    user_id TEXT PRIMARY KEY,
    amount INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0)
);

CREATE TABLE IF NOT EXISTS gamble_stats (
    user_id TEXT PRIMARY KEY,
    gains INTEGER NOT NULL DEFAULT 0 CHECK (gains >= 0),
    losses INTEGER NOT NULL DEFAULT 0 CHECK (losses >= 0)
);

CREATE TABLE IF NOT EXISTS collectibles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    attachment_urls TEXT NOT NULL DEFAULT '[]',
    embed_data TEXT NOT NULL DEFAULT '[]',
    message_url TEXT NOT NULL DEFAULT '',
    sent_at INTEGER NOT NULL,
    owner_id TEXT NOT NULL,
    claimed_at INTEGER NOT NULL,
    UNIQUE (guild_id, message_id)
);

CREATE INDEX IF NOT EXISTS collectibles_owner_idx
    ON collectibles (guild_id, owner_id, id);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES collectibles(id),
    channel_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sale', 'auction')),
    target_buyer_id TEXT,
    price INTEGER NOT NULL CHECK (price > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'sold', 'cancelled', 'expired')),
    created_at INTEGER NOT NULL,
    ends_at INTEGER,
    highest_bid INTEGER,
    highest_bidder_id TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS active_listing_per_item_idx
    ON listings (item_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS active_listings_guild_idx
    ON listings (status, kind, item_id);

CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    bidder_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS funds_holds (
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    bidder_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    PRIMARY KEY (listing_id, bidder_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    item_id INTEGER REFERENCES collectibles(id),
    listing_id INTEGER REFERENCES listings(id),
    from_user_id TEXT,
    to_user_id TEXT,
    amount INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    created_at INTEGER NOT NULL
);
"""


def now_timestamp():
    return int(datetime.now(timezone.utc).timestamp())


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    try:
        connection.executescript(SCHEMA)
        migrate_legacy_files(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with database():
        pass


def _metadata_exists(connection, key):
    row = connection.execute(
        "SELECT 1 FROM metadata WHERE key = ?", (key,)
    ).fetchone()
    return row is not None


def _read_legacy_lines(path, expected_columns):
    if not path.exists():
        return []

    rows = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(",")
            if len(parts) != expected_columns:
                continue
            rows.append(parts)
    return rows


def migrate_legacy_files(connection):
    if not _metadata_exists(connection, "legacy_balances_migrated"):
        for user_id, amount in _read_legacy_lines(LEGACY_BALANCE_FILE, 2):
            try:
                amount = int(amount)
            except ValueError:
                continue
            if amount < 0:
                continue
            connection.execute(
                """
                INSERT INTO balances (user_id, amount)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, amount),
            )
        connection.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("legacy_balances_migrated", "1"),
        )

    if not _metadata_exists(connection, "legacy_gamble_stats_migrated"):
        for user_id, gains, losses in _read_legacy_lines(
            LEGACY_GAMBLE_STATS_FILE, 3
        ):
            try:
                gains = int(gains)
                losses = int(losses)
            except ValueError:
                continue
            if gains < 0 or losses < 0:
                continue
            connection.execute(
                """
                INSERT INTO gamble_stats (user_id, gains, losses)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, gains, losses),
            )
        connection.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("legacy_gamble_stats_migrated", "1"),
        )


def _begin_write(connection):
    connection.execute("BEGIN IMMEDIATE")


def _get_balance(connection, user_id):
    row = connection.execute(
        "SELECT amount FROM balances WHERE user_id = ?", (str(user_id),)
    ).fetchone()
    return int(row["amount"]) if row is not None else 0


def _set_balance(connection, user_id, amount):
    if amount < 0:
        raise InsufficientFundsError("A balance cannot go below zero.")
    connection.execute(
        """
        INSERT INTO balances (user_id, amount)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount
        """,
        (str(user_id), amount),
    )


def _available_balance(connection, user_id):
    held = connection.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS amount
        FROM funds_holds
        WHERE bidder_id = ?
        """,
        (str(user_id),),
    ).fetchone()["amount"]
    return _get_balance(connection, user_id) - int(held)


def read_balances():
    with database() as connection:
        rows = connection.execute(
            "SELECT user_id, amount FROM balances ORDER BY rowid"
        ).fetchall()
        return {row["user_id"]: int(row["amount"]) for row in rows}


def write_balances(balances):
    with database() as connection:
        _begin_write(connection)
        for user_id, amount in balances.items():
            _set_balance(connection, user_id, int(amount))


def adjust_balance(user_id, amount):
    with database() as connection:
        _begin_write(connection)
        if amount < 0 and -amount > _available_balance(connection, user_id):
            raise InsufficientFundsError("Not enough available burgas.")
        new_balance = _get_balance(connection, user_id) + amount
        _set_balance(connection, user_id, new_balance)
        return new_balance


def reserve_wager(user_id, amount):
    with database() as connection:
        _begin_write(connection)
        balance = _get_balance(connection, user_id)
        available = _available_balance(connection, user_id)
        if amount <= 0 or amount > available:
            return False, available
        _set_balance(connection, user_id, balance - amount)
        return True, balance - amount


def _record_gamble_result(connection, user_id, amount, won):
    connection.execute(
        """
        INSERT INTO gamble_stats (user_id, gains, losses)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            gains = gains + excluded.gains,
            losses = losses + excluded.losses
        """,
        (str(user_id), amount if won else 0, 0 if won else amount),
    )


def settle_wager(user_id, amount, outcome):
    if amount <= 0 or outcome not in {"win", "loss", "draw"}:
        raise ValueError("Invalid wager settlement")

    payout = {"win": amount * 2, "loss": 0, "draw": amount}[outcome]
    with database() as connection:
        _begin_write(connection)
        new_balance = _get_balance(connection, user_id) + payout
        _set_balance(connection, user_id, new_balance)
        if outcome != "draw":
            _record_gamble_result(connection, user_id, amount, outcome == "win")
        return new_balance


def play_gamble(user_id, amount, won):
    with database() as connection:
        _begin_write(connection)
        balance = _get_balance(connection, user_id)
        available = _available_balance(connection, user_id)
        if amount <= 0 or amount > available:
            return False, available

        new_balance = balance + amount if won else balance - amount
        _set_balance(connection, user_id, new_balance)
        _record_gamble_result(connection, user_id, amount, won)
        return True, new_balance


def read_gamble_stats():
    with database() as connection:
        rows = connection.execute(
            "SELECT user_id, gains, losses FROM gamble_stats ORDER BY rowid"
        ).fetchall()
        return {
            row["user_id"]: (int(row["gains"]), int(row["losses"]))
            for row in rows
        }


def write_gamble_stats(stats):
    with database() as connection:
        _begin_write(connection)
        for user_id, (gains, losses) in stats.items():
            if gains < 0 or losses < 0:
                raise ValueError("Gambling stats cannot be negative")
            connection.execute(
                """
                INSERT INTO gamble_stats (user_id, gains, losses)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    gains = excluded.gains,
                    losses = excluded.losses
                """,
                (str(user_id), int(gains), int(losses)),
            )


def _item_row(connection, item_id, guild_id=None):
    if guild_id is None:
        return connection.execute(
            "SELECT * FROM collectibles WHERE id = ?", (item_id,)
        ).fetchone()
    return connection.execute(
        "SELECT * FROM collectibles WHERE id = ? AND guild_id = ?",
        (item_id, str(guild_id)),
    ).fetchone()


def claim_collectible(
    guild_id,
    message_id,
    channel_id,
    author_id,
    content,
    attachment_urls,
    embed_data,
    message_url,
    sent_at,
    owner_id,
):
    if str(author_id) == str(owner_id):
        raise InvalidActionError("You cannot claim your own message.")

    with database() as connection:
        _begin_write(connection)
        existing = connection.execute(
            """
            SELECT * FROM collectibles
            WHERE guild_id = ? AND message_id = ?
            """,
            (str(guild_id), str(message_id)),
        ).fetchone()
        if existing is not None:
            return dict(existing), False

        claimed_at = now_timestamp()
        cursor = connection.execute(
            """
            INSERT INTO collectibles (
                guild_id, message_id, channel_id, author_id, content,
                attachment_urls, embed_data, message_url, sent_at,
                owner_id, claimed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                str(message_id),
                str(channel_id),
                str(author_id),
                content,
                json.dumps(attachment_urls),
                json.dumps(embed_data),
                message_url,
                int(sent_at),
                str(owner_id),
                claimed_at,
            ),
        )
        item_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO transactions (
                kind, item_id, from_user_id, to_user_id, amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("claim", item_id, None, str(owner_id), 0, claimed_at),
        )
        return dict(_item_row(connection, item_id)), True


def get_item(item_id, guild_id=None):
    with database() as connection:
        row = _item_row(connection, item_id, guild_id)
        return dict(row) if row is not None else None


def get_collection(guild_id, owner_id):
    with database() as connection:
        rows = connection.execute(
            """
            SELECT * FROM collectibles
            WHERE guild_id = ? AND owner_id = ?
            ORDER BY claimed_at DESC, id DESC
            """,
            (str(guild_id), str(owner_id)),
        ).fetchall()
        return [dict(row) for row in rows]


def create_listing(
    guild_id,
    item_id,
    channel_id,
    seller_id,
    kind,
    price,
    duration_minutes=None,
    target_buyer_id=None,
):
    if kind not in {"sale", "auction"}:
        raise InvalidActionError("Unknown listing type.")
    if price <= 0:
        raise InvalidActionError("The price must be greater than zero.")
    if kind == "auction" and (
        duration_minutes is None or duration_minutes <= 0
    ):
        raise InvalidActionError("The auction duration must be positive.")
    if kind == "sale" and duration_minutes is not None:
        raise InvalidActionError("A fixed-price sale cannot have a duration.")

    with database() as connection:
        _begin_write(connection)
        item = _item_row(connection, item_id, guild_id)
        if item is None:
            raise NotFoundError(f"Collectible #{item_id} does not exist here.")
        if item["owner_id"] != str(seller_id):
            raise NotOwnerError("You do not own that collectible.")

        active = connection.execute(
            "SELECT id FROM listings WHERE item_id = ? AND status = 'active'",
            (item_id,),
        ).fetchone()
        if active is not None:
            raise ConflictError("That collectible is already listed.")

        ends_at = (
            now_timestamp() + int(duration_minutes) * 60
            if kind == "auction"
            else None
        )
        cursor = connection.execute(
            """
            INSERT INTO listings (
                item_id, channel_id, seller_id, kind, target_buyer_id,
                price, created_at, ends_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                str(channel_id),
                str(seller_id),
                kind,
                str(target_buyer_id) if target_buyer_id is not None else None,
                price,
                now_timestamp(),
                ends_at,
            ),
        )
        row = connection.execute(
            "SELECT * FROM listings WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def _transfer_money(connection, buyer_id, seller_id, amount):
    if amount < 0:
        raise InvalidActionError("The price cannot be negative.")
    if amount == 0:
        return
    if _available_balance(connection, buyer_id) < amount:
        raise InsufficientFundsError("The buyer does not have enough available burgas.")

    _set_balance(connection, buyer_id, _get_balance(connection, buyer_id) - amount)
    _set_balance(connection, seller_id, _get_balance(connection, seller_id) + amount)


def transfer_collectible(guild_id, item_id, seller_id, buyer_id, price):
    if str(seller_id) == str(buyer_id):
        raise InvalidActionError("You cannot transfer a collectible to yourself.")
    if price < 0:
        raise InvalidActionError("The price cannot be negative.")

    with database() as connection:
        _begin_write(connection)
        item = _item_row(connection, item_id, guild_id)
        if item is None:
            raise NotFoundError(f"Collectible #{item_id} does not exist here.")
        if item["owner_id"] != str(seller_id):
            raise NotOwnerError("You do not own that collectible.")

        active = connection.execute(
            "SELECT id FROM listings WHERE item_id = ? AND status = 'active'",
            (item_id,),
        ).fetchone()
        if active is not None:
            raise ConflictError("Cancel its active listing before transferring it.")

        _transfer_money(connection, buyer_id, seller_id, price)
        connection.execute(
            "UPDATE collectibles SET owner_id = ? WHERE id = ?",
            (str(buyer_id), item_id),
        )
        connection.execute(
            """
            INSERT INTO transactions (
                kind, item_id, from_user_id, to_user_id, amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("gift" if price == 0 else "direct_sale", item_id,
             str(seller_id), str(buyer_id), price, now_timestamp()),
        )
        return dict(_item_row(connection, item_id))


def buy_listing(guild_id, listing_id, buyer_id):
    with database() as connection:
        _begin_write(connection)
        row = connection.execute(
            """
            SELECT l.*, c.guild_id, c.owner_id
            FROM listings AS l
            JOIN collectibles AS c ON c.id = l.item_id
            WHERE l.id = ? AND l.status = 'active'
            """,
            (listing_id,),
        ).fetchone()
        if row is None or row["guild_id"] != str(guild_id):
            raise NotFoundError(f"Active listing #{listing_id} does not exist here.")
        if row["kind"] != "sale":
            raise InvalidActionError("That listing is an auction; use /bid.")
        if row["seller_id"] == str(buyer_id):
            raise InvalidActionError("You cannot buy your own collectible.")
        if (
            row["target_buyer_id"] is not None
            and row["target_buyer_id"] != str(buyer_id)
        ):
            raise InvalidActionError("That sale is reserved for another member.")

        _transfer_money(connection, buyer_id, row["seller_id"], row["price"])
        connection.execute(
            "UPDATE collectibles SET owner_id = ? WHERE id = ?",
            (str(buyer_id), row["item_id"]),
        )
        connection.execute(
            "UPDATE listings SET status = 'sold' WHERE id = ?", (listing_id,)
        )
        connection.execute(
            """
            INSERT INTO transactions (
                kind, item_id, listing_id, from_user_id, to_user_id,
                amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sale",
                row["item_id"],
                listing_id,
                row["seller_id"],
                str(buyer_id),
                row["price"],
                now_timestamp(),
            ),
        )
        return dict(row)


def place_bid(guild_id, listing_id, bidder_id, amount):
    if amount <= 0:
        raise InvalidActionError("The bid must be greater than zero.")

    with database() as connection:
        _begin_write(connection)
        row = connection.execute(
            """
            SELECT l.*, c.guild_id, c.owner_id
            FROM listings AS l
            JOIN collectibles AS c ON c.id = l.item_id
            WHERE l.id = ? AND l.status = 'active'
            """,
            (listing_id,),
        ).fetchone()
        if row is None or row["guild_id"] != str(guild_id):
            raise NotFoundError(f"Active listing #{listing_id} does not exist here.")
        if row["kind"] != "auction":
            raise InvalidActionError("That listing is fixed-price; use /buy.")
        if row["ends_at"] is not None and row["ends_at"] <= now_timestamp():
            raise InvalidActionError("That auction has ended.")
        if row["seller_id"] == str(bidder_id):
            raise InvalidActionError("You cannot bid on your own auction.")

        minimum = row["price"] if row["highest_bid"] is None else row["highest_bid"] + 1
        if amount < minimum:
            raise InvalidActionError(f"The minimum bid is {minimum} burgas.")

        old_hold_row = connection.execute(
            """
            SELECT amount FROM funds_holds
            WHERE listing_id = ? AND bidder_id = ?
            """,
            (listing_id, str(bidder_id)),
        ).fetchone()
        old_hold = int(old_hold_row["amount"]) if old_hold_row else 0
        if _available_balance(connection, bidder_id) + old_hold < amount:
            raise InsufficientFundsError(
                "You do not have enough available burgas for that bid."
            )

        previous_bidder = row["highest_bidder_id"]
        if previous_bidder is not None and previous_bidder != str(bidder_id):
            connection.execute(
                "DELETE FROM funds_holds WHERE listing_id = ? AND bidder_id = ?",
                (listing_id, previous_bidder),
            )

        connection.execute(
            """
            INSERT INTO bids (listing_id, bidder_id, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (listing_id, str(bidder_id), amount, now_timestamp()),
        )
        connection.execute(
            """
            INSERT INTO funds_holds (listing_id, bidder_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(listing_id, bidder_id) DO UPDATE SET amount = excluded.amount
            """,
            (listing_id, str(bidder_id), amount),
        )
        connection.execute(
            """
            UPDATE listings
            SET highest_bid = ?, highest_bidder_id = ?
            WHERE id = ?
            """,
            (amount, str(bidder_id), listing_id),
        )
        return dict(connection.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone())


def cancel_listing(guild_id, listing_id, seller_id):
    with database() as connection:
        _begin_write(connection)
        row = connection.execute(
            """
            SELECT l.*, c.guild_id
            FROM listings AS l
            JOIN collectibles AS c ON c.id = l.item_id
            WHERE l.id = ? AND l.status = 'active'
            """,
            (listing_id,),
        ).fetchone()
        if row is None or row["guild_id"] != str(guild_id):
            raise NotFoundError(f"Active listing #{listing_id} does not exist here.")
        if row["seller_id"] != str(seller_id):
            raise NotOwnerError("Only the seller can cancel this listing.")
        if row["kind"] == "auction" and row["highest_bidder_id"] is not None:
            raise ConflictError("An auction with bids cannot be cancelled.")

        connection.execute(
            "UPDATE listings SET status = 'cancelled' WHERE id = ?", (listing_id,)
        )
        connection.execute(
            "DELETE FROM funds_holds WHERE listing_id = ?", (listing_id,)
        )
        return dict(row)


def get_market_listings(guild_id):
    with database() as connection:
        rows = connection.execute(
            """
            SELECT l.*, c.guild_id, c.content, c.message_url
            FROM listings AS l
            JOIN collectibles AS c ON c.id = l.item_id
            WHERE c.guild_id = ? AND l.status = 'active'
            ORDER BY l.kind, l.id
            """,
            (str(guild_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def close_expired_auctions(timestamp=None):
    timestamp = now_timestamp() if timestamp is None else timestamp
    outcomes = []

    with database() as connection:
        _begin_write(connection)
        rows = connection.execute(
            """
            SELECT l.*, c.guild_id, c.owner_id
            FROM listings AS l
            JOIN collectibles AS c ON c.id = l.item_id
            WHERE l.kind = 'auction'
              AND l.status = 'active'
              AND l.ends_at IS NOT NULL
              AND l.ends_at <= ?
            ORDER BY l.id
            """,
            (timestamp,),
        ).fetchall()

        for row in rows:
            status = "expired"
            winner_id = row["highest_bidder_id"]
            amount = row["highest_bid"] or 0

            if winner_id is not None and amount > 0:
                connection.execute(
                    "DELETE FROM funds_holds WHERE listing_id = ? AND bidder_id = ?",
                    (row["id"], winner_id),
                )
                if _available_balance(connection, winner_id) < amount:
                    winner_id = None
                    amount = 0
                else:
                    _transfer_money(connection, winner_id, row["seller_id"], amount)
                    connection.execute(
                        "UPDATE collectibles SET owner_id = ? WHERE id = ?",
                        (winner_id, row["item_id"]),
                    )
                    connection.execute(
                        """
                        INSERT INTO transactions (
                            kind, item_id, listing_id, from_user_id, to_user_id,
                            amount, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "auction",
                            row["item_id"],
                            row["id"],
                            row["seller_id"],
                            winner_id,
                            amount,
                            now_timestamp(),
                        ),
                    )
                    status = "sold"

            connection.execute(
                "UPDATE listings SET status = ? WHERE id = ?",
                (status, row["id"]),
            )
            connection.execute(
                "DELETE FROM funds_holds WHERE listing_id = ?", (row["id"],)
            )
            outcomes.append(
                {
                    "listing_id": row["id"],
                    "item_id": row["item_id"],
                    "channel_id": row["channel_id"],
                    "status": status,
                    "winner_id": winner_id,
                    "amount": amount,
                }
            )

    return outcomes
