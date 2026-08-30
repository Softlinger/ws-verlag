from fastapi.templating import Jinja2Templates

from app.version import __version__

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_version"] = __version__
