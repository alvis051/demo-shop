import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cart as carts
from app import payments
from app.auth import require_user
from app.db import get_session
from app.models import CheckoutAttempt, CouponRedemption, Order, OrderLine, Product, User
from app.web import flash, redirect, render

router = APIRouter(prefix="/checkout")

FIELDS = ("name", "address", "card_number", "expiry", "cvc")


def _token(request: Request) -> str:
    if "checkout_token" not in request.session:
        request.session["checkout_token"] = secrets.token_urlsafe(24)
    return request.session["checkout_token"]


def _validate(form: dict[str, str]) -> dict[str, str]:
    errors = {}
    if not form["name"]:
        errors["name"] = "Enter the name for delivery."
    if len(form["address"]) < 10:
        errors["address"] = "Enter the full delivery address."
    if not payments.is_known_card(form["card_number"]):
        errors["card_number"] = "Enter a valid card number."
    match = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", form["expiry"])
    if not match or not 1 <= int(match[1]) <= 12:
        errors["expiry"] = "Enter the expiry date as MM/YY."
    else:
        now = datetime.now(UTC)
        if (2000 + int(match[2]), int(match[1])) < (now.year, now.month):
            errors["expiry"] = "This card has expired."
    if not re.fullmatch(r"\d{3,4}", form["cvc"]):
        errors["cvc"] = "Enter the 3 or 4 digit security code."
    return errors


def _form_page(request, user, totals, form, errors=None, payment_error=None, status=200):
    return render(
        request,
        "checkout.html",
        status,
        user=user,
        totals=totals,
        form=form,
        errors=errors or {},
        payment_error=payment_error,
        token=_token(request),
    )


@router.get("")
def checkout_form(request: Request, db: Session = Depends(get_session), user: User = Depends(require_user)):
    totals = carts.totals(db, request.session, user)
    if not totals.lines:
        flash(request, "Your cart is empty.", "error")
        return redirect("/cart")
    form = dict.fromkeys(FIELDS, "") | {"name": user.name}
    return _form_page(request, user, totals, form)


@router.post("")
def place_order(
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    card_number: str = Form(""),
    expiry: str = Form(""),
    cvc: str = Form(""),
    token: str = Form(""),
    db: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    if request.app.state.faults.flaky_hit():
        raise HTTPException(503, "We couldn't reach the payment service. Please try again in a moment.")
    form = {
        "name": name.strip(),
        "address": address.strip(),
        "card_number": card_number.strip(),
        "expiry": expiry.strip(),
        "cvc": cvc.strip(),
    }

    # A second submit of a form that already went through goes to its order.
    existing = db.scalar(select(Order).where(Order.checkout_token == token, Order.user_id == user.id))
    if existing:
        return redirect(f"/orders/{existing.id}")
    if not token or token != request.session.get("checkout_token"):
        flash(request, "This checkout form has expired. Please check your order and try again.", "error")
        return redirect("/checkout")

    totals = carts.totals(db, request.session, user)
    if not totals.lines:
        flash(request, "Your cart is empty.", "error")
        return redirect("/cart")
    if totals.coupon_error:
        request.session.pop("coupon", None)
        flash(request, f"{totals.coupon_error} It has been removed from your cart.", "error")
        return redirect("/cart")
    errors = _validate(form)
    if errors:
        return _form_page(request, user, totals, form, errors, status=422)

    card = payments.normalize_card(form["card_number"])
    attempt = 1
    if card == payments.RETRYABLE_CARD:
        attempt = db.scalar(
            insert(CheckoutAttempt)
            .values(token=token, user_id=user.id, attempts=1)
            .on_conflict_do_update(index_elements=["token"], set_={"attempts": CheckoutAttempt.attempts + 1})
            .returning(CheckoutAttempt.attempts)
        )
        db.commit()

    # Lock the products, check stock, charge, then write the order in one transaction.
    ids = sorted(line.product.id for line in totals.lines)
    locked = {
        p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)).order_by(Product.id).with_for_update())
    }
    short = [line for line in totals.lines if locked[line.product.id].stock < line.qty]
    if short:
        db.rollback()
        for line in short:
            carts.set_qty(request.session, locked[line.product.id], line.qty)
        flash(
            request,
            "Some items in your cart are no longer available in that quantity. Your cart has been updated.",
            "error",
        )
        return redirect("/cart")

    outcome = payments.charge(card, totals.total_cents, attempt)
    if outcome is not payments.Outcome.APPROVED:
        db.rollback()
        message = (
            "Your card was declined. Try a different card."
            if outcome is payments.Outcome.DECLINED
            else "The payment provider had a temporary problem and your card wasn't charged. Please try again."
        )
        return _form_page(request, user, totals, form, payment_error=message, status=402)

    order = Order(
        user_id=user.id,
        checkout_token=token,
        subtotal_cents=totals.subtotal_cents,
        discount_cents=totals.discount_cents,
        total_cents=totals.total_cents,
        coupon_code=totals.coupon.code if totals.coupon else None,
        ship_name=form["name"],
        ship_address=form["address"],
        card_last4=card[-4:],
        lines=[
            OrderLine(
                product_id=line.product.id,
                name=line.product.name,
                unit_price_cents=line.product.price_cents,
                quantity=line.qty,
            )
            for line in totals.lines
        ],
    )
    for line in totals.lines:
        locked[line.product.id].stock -= line.qty
    db.add(order)
    try:
        db.flush()
        if totals.coupon and totals.coupon.once_per_user:
            db.add(CouponRedemption(coupon_id=totals.coupon.id, user_id=user.id, order_id=order.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Order).where(Order.checkout_token == token))
        if existing and existing.user_id == user.id:
            return redirect(f"/orders/{existing.id}")
        flash(request, "We couldn't place your order. Please check your cart and try again.", "error")
        return redirect("/cart")

    for key in ("cart", "coupon", "checkout_token"):
        request.session.pop(key, None)
    flash(request, f"Thank you! Your order #{order.id} has been placed.", "success")
    return redirect(f"/orders/{order.id}")
