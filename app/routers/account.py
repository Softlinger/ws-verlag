from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password, require_login, verify_password
from app.database import get_db
from app.models import User
from app.templating import templates

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/password")
def change_password_form(request: Request, user: User = Depends(require_login)):
    return templates.TemplateResponse(request, "account/password.html", {"error": None, "success": False})


@router.post("/password")
def change_password_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
):
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "account/password.html",
            {"error": "Aktuelles Passwort ist falsch.", "success": False},
            status_code=401,
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "account/password.html",
            {"error": "Neues Passwort muss mindestens 8 Zeichen lang sein.", "success": False},
            status_code=400,
        )
    if new_password != new_password_confirm:
        return templates.TemplateResponse(
            request,
            "account/password.html",
            {"error": "Die beiden neuen Passwörter stimmen nicht überein.", "success": False},
            status_code=400,
        )

    user.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(request, "account/password.html", {"error": None, "success": True})
