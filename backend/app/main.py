from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.infrastructure.scheduler.medicine_rectify_scheduler import medicine_rectify_scheduler

app = FastAPI(title=settings.app_name)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],  # Frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)

WEB_ROOT = Path(__file__).resolve().parent / "web"
MONITOR_HTML_PATH = WEB_ROOT / "monitor.html"
QC_WEB_ROOT = WEB_ROOT / "qc"
QC_LOGIN_HTML_PATH = QC_WEB_ROOT / "login.html"
QC_WORKSPACE_HTML_PATH = QC_WEB_ROOT / "workspace.html"

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIST_ROOT = REPO_ROOT / "verifAI-UI" / "dist"
UI_INDEX_PATH = UI_DIST_ROOT / "index.html"


def _ui_dist_ready() -> bool:
    return UI_INDEX_PATH.exists() and UI_INDEX_PATH.is_file()


def _react_index_response() -> HTMLResponse:
    return HTMLResponse(
        content=UI_INDEX_PATH.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

app.mount(
    "/qc/public", StaticFiles(directory=str(QC_WEB_ROOT / "public")), name="qc_public"
)
if (UI_DIST_ROOT / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST_ROOT / "assets")), name="ui_assets")


@app.on_event("startup")
async def on_startup() -> None:
    medicine_rectify_scheduler.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await medicine_rectify_scheduler.stop()


@app.get("/")
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/qc/login", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    return RedirectResponse(
        url="/qc/public/assets/report-signature.png", status_code=307
    )


@app.get("/monitor", response_class=HTMLResponse)
def monitor_ui() -> str:
    if _ui_dist_ready():
        return _react_index_response()
    return MONITOR_HTML_PATH.read_text(encoding="utf-8")


@app.get("/qc")
def qc_index() -> RedirectResponse:
    return RedirectResponse(url="/qc/login")


@app.get("/qc/admin")
def qc_admin_index() -> RedirectResponse:
    return RedirectResponse(url="/qc/super_admin/dashboard")


@app.get("/qc/admin/{path:path}")
def qc_admin_legacy_redirect(path: str) -> RedirectResponse:
    suffix = path.strip("/") or "dashboard"
    return RedirectResponse(url=f"/qc/super_admin/{suffix}")


@app.get("/qc/login", response_class=HTMLResponse)
def qc_login_ui() -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    return HTMLResponse(
        content=QC_LOGIN_HTML_PATH.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/qc/{path:path}", response_class=HTMLResponse)
def qc_workspace_ui(path: str) -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    if path == "" or path == "login":
        return HTMLResponse(
            content=QC_LOGIN_HTML_PATH.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return HTMLResponse(
        content=QC_WORKSPACE_HTML_PATH.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/login", response_class=HTMLResponse)
def react_login_entry() -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    return RedirectResponse(url="/qc/login", status_code=307)


@app.get("/app/{path:path}", response_class=HTMLResponse)
def react_app_entry(path: str) -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    return RedirectResponse(url="/qc/login", status_code=307)


@app.get("/report-editor", response_class=HTMLResponse)
def react_report_editor_entry() -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    return RedirectResponse(url="/qc/login", status_code=307)


@app.get("/auditor-qc", response_class=HTMLResponse)
def react_auditor_qc_entry() -> HTMLResponse:
    if _ui_dist_ready():
        return _react_index_response()
    return RedirectResponse(url="/qc/login", status_code=307)
