from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.infrastructure.scheduler.medicine_rectify_scheduler import medicine_rectify_scheduler

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

app.mount(
    "/qc/public", StaticFiles(directory=str(QC_WEB_ROOT / "public")), name="qc_public"
)


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
def monitor_ui() -> HTMLResponse:
    return HTMLResponse(
        content=MONITOR_HTML_PATH.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


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
