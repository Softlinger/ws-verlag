from fastapi import APIRouter, Depends, Request

from app.auth import require_login
from app.models import User
from app.templating import templates

router = APIRouter(prefix="/help", tags=["help"])


@router.get("")
def help_page(request: Request, user: User = Depends(require_login)):
    return templates.TemplateResponse(request, "help/page.html", {})
