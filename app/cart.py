"""Session cart and pricing. All money is in integer cents."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Coupon, CouponRedemption, Product, User

MAX_QTY = 99


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def get_cart(session: dict) -> dict[str, int]:
    return session.setdefault("cart", {})


def cart_count(session: dict) -> int:
    return sum(session.get("cart", {}).values())


def set_qty(session: dict, product: Product, qty: int) -> tuple[int, str | None]:
    """Set a line's quantity, capped at stock. Returns the quantity set and a note if capped."""
    cart = get_cart(session)
    qty = max(0, min(qty, MAX_QTY))
    note = None
    if qty > product.stock:
        qty = product.stock
        note = f"Only {product.stock} of {product.name} in stock, so your cart has {qty}."
    if qty == 0:
        cart.pop(str(product.id), None)
    else:
        cart[str(product.id)] = qty
    session["cart"] = cart
    return qty, note


@dataclass
class Line:
    product: Product
    qty: int

    @property
    def total_cents(self) -> int:
        return self.product.price_cents * self.qty


@dataclass
class Totals:
    lines: list[Line] = field(default_factory=list)
    coupon: Coupon | None = None
    coupon_error: str | None = None
    discount_cents: int = 0

    @property
    def subtotal_cents(self) -> int:
        return sum(line.total_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents - self.discount_cents

    @property
    def count(self) -> int:
        return sum(line.qty for line in self.lines)


def cart_lines(db: Session, session: dict) -> list[Line]:
    cart = get_cart(session)
    if not cart:
        return []
    products = db.scalars(select(Product).where(Product.id.in_([int(k) for k in cart]))).all()
    found = {str(p.id): p for p in products}
    # Drop products that no longer exist.
    for key in list(cart):
        if key not in found:
            cart.pop(key)
    session["cart"] = cart
    return [Line(found[k], q) for k, q in cart.items()]


def check_coupon(db: Session, code: str, user: User | None, subtotal_cents: int) -> tuple[Coupon | None, str | None]:
    code = code.strip().upper()
    if not code:
        return None, "Enter a coupon code."
    coupon = db.scalar(select(Coupon).where(Coupon.code == code))
    if coupon is None:
        return None, f"Coupon code {code} isn't valid."
    if coupon.expires_at and coupon.expires_at <= datetime.now(UTC):
        return None, f"Coupon {code} has expired."
    if subtotal_cents < coupon.min_subtotal_cents:
        return None, f"Coupon {code} needs a subtotal of at least {money(coupon.min_subtotal_cents)}."
    if coupon.once_per_user and user is not None:
        used = db.scalar(
            select(CouponRedemption.id).where(
                CouponRedemption.coupon_id == coupon.id, CouponRedemption.user_id == user.id
            )
        )
        if used:
            return None, f"You've already used coupon {code}."
    return coupon, None


def discount_for(coupon: Coupon, subtotal_cents: int) -> int:
    if coupon.kind == "percent":
        return subtotal_cents * coupon.amount // 100
    return min(coupon.amount, subtotal_cents)


def totals(db: Session, session: dict, user: User | None) -> Totals:
    result = Totals(lines=cart_lines(db, session))
    code = session.get("coupon")
    if code and result.lines:
        coupon, error = check_coupon(db, code, user, result.subtotal_cents)
        if coupon:
            result.coupon = coupon
            result.discount_cents = discount_for(coupon, result.subtotal_cents)
        else:
            result.coupon_error = error
    return result
