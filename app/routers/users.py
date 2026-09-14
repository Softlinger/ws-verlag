from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.templating import templates

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(require_admin)):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.username.ilike(like), User.full_name.ilike(like)))
    users = query.order_by(User.username).all()
    return templates.TemplateResponse(request, "users/list.html", {"users": users, "q": q})


@router.get("/new")
def new_user_form(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse(request, "users/form.html", {"edit_user": None, "roles": list(UserRole)})


@router.post("/new")
def create_user(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: UserRole = Form(UserRole.SACHBEARBEITER),
):
    if len(password) < 8:
        return RedirectResponse("/users?error=password_too_short", status_code=303)
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse("/users?error=username_exists", status_code=303)
    new_user = User(username=username, full_name=full_name, password_hash=hash_password(password), role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/deactivate")
def deactivate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target:
        target.active = False
        # Bestehende Sessions des Benutzers sofort entwerten (password_version hoch).
        target.password_version = (target.password_version or 0) + 1
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/activate")
def activate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target:
        target.active = True
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    new_password: str = Form(...),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/users", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse(f"/users?error=password_too_short#user-{target.id}", status_code=303)
    target.password_hash = hash_password(new_password)
    target.password_version = (target.password_version or 0) + 1
    db.commit()
    return RedirectResponse(f"/users?success=password_reset#user-{target.id}", status_code=303)
