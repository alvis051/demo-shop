from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, safe_next, verify_password
from app.db import get_session
from app.models import User
from app.web import flash, redirect, render

router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/", user: User | None = Depends(current_user)):
    if user:
        return redirect(safe_next(next))
    return render(request, "login.html", user=None, next=safe_next(next), email="", error=None)


@router.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_session),
):
    email = email.strip()
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower())) if email else None
    if user is None or not verify_password(password, user.password_hash):
        error = "Enter your email and password." if not email or not password else "Incorrect email or password."
        return render(request, "login.html", 401, user=None, next=safe_next(next), email=email, error=error)
    # Keep the cart, drop everything else from the anonymous session.
    cart = request.session.get("cart", {})
    coupon = request.session.get("coupon")
    request.session.clear()
    request.session.update(user_id=user.id, cart=cart)
    if coupon:
        request.session["coupon"] = coupon
    flash(request, f"Welcome back, {user.name}.")
    return redirect(safe_next(next))


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "You've been signed out.")
    return redirect("/")
