from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.csrf import COOKIE_NAME, create_token
from app.version import __version__

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_version"] = __version__
templates.env.globals["csrf_cookie_name"] = COOKIE_NAME


def csrf_field(request) -> Markup:
    """Verstecktes CSRF-Feld fuer POST-Formulare: {{ csrf_field(request) }}.

    Liest den vom Middleware bereitgestellten Token (request.state.csrf_token);
    itsdangerous-URLSafe-Token enthaelt nur HTML-Attribut-sichere Zeichen."""
    token = getattr(request.state, "csrf_token", None) or create_token()
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


templates.env.globals["csrf_field"] = csrf_field
