"""Fake payment gateway. The card number decides the outcome, like a test-mode gateway."""

from enum import StrEnum

APPROVED_CARD = "4242424242424242"
DECLINED_CARD = "4000000000000002"
RETRYABLE_CARD = "4000000000000119"


class Outcome(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"
    RETRY = "retry"


def normalize_card(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())


def is_known_card(number: str) -> bool:
    return normalize_card(number) in (APPROVED_CARD, DECLINED_CARD, RETRYABLE_CARD)


def charge(card_number: str, amount_cents: int, attempt: int) -> Outcome:
    """`attempt` counts from 1 for each checkout token."""
    card = normalize_card(card_number)
    if card == DECLINED_CARD:
        return Outcome.DECLINED
    if card == RETRYABLE_CARD and attempt == 1:
        return Outcome.RETRY
    return Outcome.APPROVED
