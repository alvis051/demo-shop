from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_session
from app.models import Product, User
from app.web import render

router = APIRouter()

SORTS = {
    "featured": ("Featured", Product.id),
    "price-asc": ("Price: low to high", Product.price_cents),
    "price-desc": ("Price: high to low", Product.price_cents.desc()),
    "name": ("Name", Product.name),
}


@router.get("/")
def catalog(
    request: Request,
    q: str = "",
    category: str = "",
    sort: str = "featured",
    db: Session = Depends(get_session),
    user: User | None = Depends(current_user),
):
    query = select(Product)
    q = q.strip()
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(Product.name.ilike(pattern), Product.description.ilike(pattern), Product.category.ilike(pattern))
        )
    if category:
        query = query.where(Product.category == category)
    if sort not in SORTS:
        sort = "featured"
    products = db.scalars(query.order_by(SORTS[sort][1], Product.id)).all()
    categories = db.scalars(select(Product.category).distinct().order_by(Product.category)).all()
    return render(
        request,
        "catalog.html",
        user=user,
        products=products,
        categories=categories,
        sorts={key: label for key, (label, _) in SORTS.items()},
        q=q,
        category=category,
        sort=sort,
    )


@router.get("/products/{product_id}")
def product_detail(
    request: Request,
    product_id: int,
    db: Session = Depends(get_session),
    user: User | None = Depends(current_user),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404)
    in_cart = request.session.get("cart", {}).get(str(product.id), 0)
    return render(request, "product.html", user=user, product=product, in_cart=in_cart)
