"""Seed data. Safe to run again: rows that already exist are left alone.

Run with `python -m app.seed` after migrations.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.auth import hash_password
from app.config import Settings, get_settings

PRODUCTS = [
    (
        "COF-001",
        "House Blend Coffee",
        "Coffee",
        1499,
        40,
        "Medium roast with notes of cocoa and toasted nuts. 340 g whole bean.",
    ),
    (
        "COF-002",
        "Ethiopia Yirgacheffe",
        "Coffee",
        1899,
        25,
        "Light roast, floral and bright with a lemon finish. 340 g whole bean.",
    ),
    ("COF-003", "Colombia Decaf", "Coffee", 1650, 3, "Swiss Water decaf with caramel sweetness. 340 g whole bean."),
    ("COF-004", "Espresso Forte", "Coffee", 1750, 0, "Dark roast built for espresso, syrupy body. 340 g whole bean."),
    ("TEA-001", "Sencha Green Tea", "Tea", 1200, 30, "Steamed Japanese green tea, grassy and sweet. 100 g loose leaf."),
    ("TEA-002", "Earl Grey", "Tea", 999, 50, "Black tea with bergamot oil. 100 g loose leaf."),
    ("TEA-003", "Chamomile Blossoms", "Tea", 899, 20, "Whole chamomile flowers for a caffeine-free evening cup. 50 g."),
    ("TEA-004", "Masala Chai", "Tea", 1099, 15, "Assam black tea with cardamom, ginger and cinnamon. 100 g."),
    ("GEAR-001", "Pour-Over Dripper", "Gear", 2400, 12, "Ceramic cone dripper for size 02 filters."),
    ("GEAR-002", "Burr Grinder", "Gear", 8900, 5, "Hand grinder with steel conical burrs and 40 grind settings."),
    ("GEAR-003", "Gooseneck Kettle", "Gear", 4500, 8, "1 litre stovetop kettle with a precise pouring spout."),
    ("GEAR-004", "Paper Filters (100)", "Gear", 650, 100, "Unbleached size 02 paper filters, pack of 100."),
]

COUPONS = [
    # code, kind, amount, min subtotal (cents), expires at, once per user
    ("SAVE10", "percent", 10, 0, None, False),
    ("FIVEOFF", "fixed", 500, 2500, None, False),
    ("EXPIRED", "percent", 20, 0, datetime(2020, 1, 1, tzinfo=UTC), False),
    ("WELCOME", "percent", 15, 0, None, True),
]

DEMO_USERS = [
    ("alice@example.com", "Alice Example", "alice-pass"),
    ("bob@example.com", "Bob Example", "bob-pass"),
]


def seed(session: Session, settings: Settings) -> None:
    session.execute(
        insert(models.Product)
        .values(
            [
                dict(sku=sku, name=name, category=cat, price_cents=price, stock=stock, description=desc)
                for sku, name, cat, price, stock, desc in PRODUCTS
            ]
        )
        .on_conflict_do_nothing(index_elements=["sku"])
    )
    session.execute(
        insert(models.Coupon)
        .values(
            [
                dict(
                    code=code, kind=kind, amount=amount, min_subtotal_cents=minimum, expires_at=exp, once_per_user=once
                )
                for code, kind, amount, minimum, exp, once in COUPONS
            ]
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )
    users = [(settings.admin_email, "Shop Admin", settings.admin_password, True)]
    if settings.seed_demo_users:
        users += [(email, name, password, False) for email, name, password in DEMO_USERS]
    session.execute(
        insert(models.User)
        .values(
            [
                dict(email=email, name=name, password_hash=hash_password(password), is_admin=admin)
                for email, name, password, admin in users
            ]
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )
    session.commit()


def reset(session: Session, settings: Settings) -> None:
    """Delete all data and seed again, with ids starting from 1. Never used in prod."""
    tables = ", ".join(t.name for t in models.Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    seed(session, settings)


if __name__ == "__main__":
    from app.db import Database

    settings = get_settings()
    db = Database(settings)
    if db.schema:
        raise SystemExit("python -m app.seed is for deployed environments; test runs seed themselves")
    with db.sessions() as session:
        seed(session, settings)
    db.engine.dispose()
    print(f"Seeded {settings.env}")
