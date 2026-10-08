from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_session
from app.faults import Faults
from app.models import User
from app.seed import reset
from app.web import flash, redirect, render

router = APIRouter(prefix="/admin")


def faults_allowed(request: Request) -> Faults:
    faults: Faults = request.app.state.faults
    if not faults.allowed:
        raise HTTPException(404)
    return faults


@router.get("/faults")
def faults_page(request: Request, user: User = Depends(require_admin), faults: Faults = Depends(faults_allowed)):
    return render(request, "admin.html", user=user, faults=faults)


@router.post("/faults")
def update_faults(
    request: Request,
    latency_ms: int = Form(0),
    flaky_rate: float = Form(0.0),
    bug: str = Form(""),
    user: User = Depends(require_admin),
    faults: Faults = Depends(faults_allowed),
):
    if latency_ms < 0 or not 0 <= flaky_rate <= 1:
        flash(request, "Latency must be 0 or more and the flaky rate between 0 and 1.", "error")
        return redirect("/admin/faults")
    faults.update(latency_ms, flaky_rate, bug)
    flash(request, "Fault settings saved.", "success")
    return redirect("/admin/faults")


@router.post("/reset")
def reset_data(
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
    faults: Faults = Depends(faults_allowed),
):
    reset(db, request.app.state.settings)
    request.session.clear()
    flash(request, "All data has been reset. Sign in again to continue.", "success")
    return redirect("/login")
