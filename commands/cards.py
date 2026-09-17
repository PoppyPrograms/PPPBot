from random import shuffle


RANKS = (
    "A",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "J",
    "Q",
    "K",
)
SUITS = ("♠", "♥", "♦", "♣")
CARD_BACK = "🂠"


def new_deck():
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    shuffle(deck)
    return deck


def card_text(card):
    return f"{card[0]}{card[1]}"


def hand_text(hand):
    return " ".join(card_text(card) for card in hand)
