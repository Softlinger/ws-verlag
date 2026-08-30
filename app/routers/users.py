from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.templating import templates

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse(request, "users/list.html", {"users": users})


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
    new_user = User(username=username, full_name=full_name, password_hash=hash_password(password), role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/deactivate")
def deactivate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target:
        target.active = False
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/activate")
def activate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target:
        target.active = True
        db.commit()
    return RedirectResponse("/users", status_code=303)
