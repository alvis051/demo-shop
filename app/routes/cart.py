from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app import cart as carts
from app.auth import current_user
from app.db import get_session
from app.models import Product, User
from app.web import flash, redirect, render

router = APIRouter(prefix="/cart")


def _product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "That product no longer exists.")
    return product


@router.get("")
def view_cart(request: Request, db: Session = Depends(get_session), user: User | None = Depends(current_user)):
    totals = carts.totals(db, request.session, user)
    return render(request, "cart.html", user=user, totals=totals, max_qty=carts.MAX_QTY)


@router.post("/add")
def add(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_session),
):
    product = _product(db, product_id)
    if product.stock == 0:
        flash(request, f"{product.name} is out of stock.", "error")
        return redirect(f"/products/{product.id}")
    if quantity < 1:
        flash(request, "Quantity must be at least 1.", "error")
        return redirect(f"/products/{product.id}")
    current = carts.get_cart(request.session).get(str(product.id), 0)
    qty, note = carts.set_qty(request.session, product, current + quantity)
    if note:
        flash(request, note, "error")
    else:
        flash(request, f"Added {quantity} × {product.name} to your cart.")
    return redirect("/cart")


@router.post("/update")
def update(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_session),
):
    product = _product(db, product_id)
    qty, note = carts.set_qty(request.session, product, quantity)
    if note:
        flash(request, note, "error")
    elif qty == 0:
        flash(request, f"Removed {product.name} from your cart.")
    else:
        flash(request, f"Updated {product.name} to {qty}.")
    return redirect("/cart")


@router.post("/remove")
def remove(request: Request, product_id: int = Form(...), db: Session = Depends(get_session)):
    product = _product(db, product_id)
    carts.set_qty(request.session, product, 0)
    flash(request, f"Removed {product.name} from your cart.")
    return redirect("/cart")


@router.post("/coupon")
def apply_coupon(
    request: Request,
    code: str = Form(""),
    db: Session = Depends(get_session),
    user: User | None = Depends(current_user),
):
    totals = carts.totals(db, request.session, user)
    if not totals.lines:
        flash(request, "Add something to your cart before using a coupon.", "error")
        return redirect("/cart")
    coupon, error = carts.check_coupon(db, code, user, totals.subtotal_cents)
    if error:
        flash(request, error, "error")
    else:
        request.session["coupon"] = coupon.code
        flash(request, f"Coupon {coupon.code} applied.")
    return redirect("/cart")


@router.post("/coupon/remove")
def remove_coupon(request: Request):
    if request.session.pop("coupon", None):
        flash(request, "Coupon removed.")
    return redirect("/cart")
