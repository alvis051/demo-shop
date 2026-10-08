from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_user
from app.db import get_session
from app.models import Order, User
from app.web import render

router = APIRouter(prefix="/orders")


@router.get("")
def list_orders(request: Request, db: Session = Depends(get_session), user: User = Depends(require_user)):
    orders = db.scalars(
        select(Order)
        .where(Order.user_id == user.id)
        .options(selectinload(Order.lines))
        .order_by(Order.created_at.desc(), Order.id.desc())
    ).all()
    return render(request, "orders.html", user=user, orders=orders)


@router.get("/{order_id}")
def order_detail(
    request: Request, order_id: int, db: Session = Depends(get_session), user: User = Depends(require_user)
):
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == user.id).options(selectinload(Order.lines))
    )
    if order is None:
        raise HTTPException(404)
    return render(request, "order.html", user=user, order=order)
