import calendar
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import User
from app.routers.company import get_or_create_company
from app.services.pdf import render_balance_list_pdf, render_vat_summary_pdf
from app.services.reporting import balance_list_to_csv, get_balance_list, get_vat_summary, vat_summary_to_csv
from app.templating import templates

router = APIRouter(prefix="/reports", tags=["reports"])


def _default_period() -> tuple[date, date]:
    """Aktueller Monat, falls kein Zeitraum angegeben wurde."""
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last_day)


def _resolve_period(von: date | None, bis: date | None) -> tuple[date, date]:
    if von is None or bis is None:
        return _default_period()
    return von, bis


@router.get("")
def reports_index(
    request: Request,
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    return templates.TemplateResponse(
        request, "reports/index.html", {"date_from": date_from, "date_to": date_to}
    )


@router.get("/saldenliste")
def saldenliste_view(
    request: Request,
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    saldenliste = get_balance_list(db, date_from, date_to)
    return templates.TemplateResponse(request, "reports/saldenliste.html", {"saldenliste": saldenliste})


@router.get("/saldenliste/csv")
def saldenliste_csv(
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    saldenliste = get_balance_list(db, date_from, date_to)
    csv_content = balance_list_to_csv(saldenliste)
    filename = f"saldenliste_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/saldenliste/pdf")
def saldenliste_pdf(
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    saldenliste = get_balance_list(db, date_from, date_to)
    company = get_or_create_company(db)
    pdf_bytes = render_balance_list_pdf(company=company, saldenliste=saldenliste)
    filename = f"saldenliste_{date_from.isoformat()}_{date_to.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/uva")
def uva_view(
    request: Request,
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    summary = get_vat_summary(db, date_from, date_to)
    return templates.TemplateResponse(request, "reports/uva.html", {"summary": summary})


@router.get("/uva/csv")
def uva_csv(
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    summary = get_vat_summary(db, date_from, date_to)
    csv_content = vat_summary_to_csv(summary)
    filename = f"uva_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/uva/pdf")
def uva_pdf(
    db: Session = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    user: User = Depends(require_login),
):
    date_from, date_to = _resolve_period(von, bis)
    summary = get_vat_summary(db, date_from, date_to)
    company = get_or_create_company(db)
    pdf_bytes = render_vat_summary_pdf(company=company, summary=summary)
    filename = f"uva_{date_from.isoformat()}_{date_to.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
