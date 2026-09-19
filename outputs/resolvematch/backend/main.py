import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config, service, trueforge
from .store import audit, db, engineer_rows, initialize, now, ticket_row
from .tools import mcp

logger = logging.getLogger("resolvematch")
locks: dict[str, asyncio.Lock] = {}
attempts: dict[str, list[float]] = {}


async def monitor():
    while True:
        await asyncio.sleep(2)
        with db() as c:
            ids = [
                r["id"]
                for r in c.execute(
                    "SELECT id FROM tickets WHERE run_started IS NOT NULL"
                )
            ]
        for ident in ids:
            async with locks.setdefault(ident, asyncio.Lock()):
                try:
                    await trueforge.sync(ident)
                except trueforge.ForgeError:
                    logger.warning("TrueForge temporarily unreachable for %s", ident)
                except Exception:
                    logger.exception("Run monitor error for %s", ident)
                    trueforge.fail(
                        ident,
                        "Unexpected integration error. Check backend logs and the TrueForge session.",
                    )


@asynccontextmanager
async def lifespan(app):
    initialize()
    async with mcp.session_manager.run():
        task = asyncio.create_task(monitor())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ResolveMatch", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "testserver",
        config.PUBLIC_ORIGIN.split("://")[-1].split(":")[0],
    ],
)


def session_valid(token):
    try:
        expiry, signature = token.split(".")
        expected = hmac.new(
            config.SESSION_KEY.encode(), expiry.encode(), hashlib.sha256
        ).hexdigest()
        return int(expiry) > time.time() and hmac.compare_digest(expected, signature)
    except (ValueError, AttributeError):
        return False


@app.middleware("http")
async def security(request: Request, call_next):
    request_id = secrets.token_hex(8)
    path = request.url.path
    if path.startswith("/mcp"):
        if not hmac.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {config.MCP_TOKEN}"
        ):
            return JSONResponse(
                {"detail": "MCP authentication required"}, status_code=401
            )
    elif path.startswith("/api"):
        if (
            config.PASSWORD
            and path not in ("/api/auth", "/api/login", "/api/health")
            and not session_valid(request.cookies.get("rm_session", ""))
        ):
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed = {
                config.PUBLIC_ORIGIN,
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            }
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
            if request.headers.get("x-resolvematch") != "1":
                return JSONResponse(
                    {"detail": "Missing request verification header"}, status_code=403
                )
            ip = request.client.host if request.client else "unknown"
            recent = [t for t in attempts.get(ip, []) if t > time.time() - 60]
            if len(recent) >= 60:
                return JSONResponse(
                    {"detail": "Too many requests. Retry in one minute."},
                    status_code=429,
                )
            attempts[ip] = recent + [time.time()]
    if int(request.headers.get("content-length", "0")) > 65536 and not path.startswith(
        "/mcp"
    ):
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        }
    )
    if path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def bad_input(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(trueforge.ForgeError)
async def forge_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketInput(StrictModel):
    title: str = Field(min_length=5, max_length=180)
    description: str = Field(min_length=15, max_length=12000)
    severity: Literal["Low", "Medium", "High", "Critical"] = "High"
    team: str = Field(default="", max_length=80)


class Decision(StrictModel):
    allow: bool
    version: int


class EngineerUpdate(StrictModel):
    available: bool
    on_call: bool
    capacity: int = Field(ge=1, le=100)


class Login(StrictModel):
    password: str = Field(max_length=300)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/auth")
def auth(request: Request):
    return {
        "required": bool(config.PASSWORD),
        "authenticated": not config.PASSWORD
        or session_valid(request.cookies.get("rm_session", "")),
    }


@app.post("/api/login")
def login(body: Login, response: Response):
    if not config.PASSWORD or not hmac.compare_digest(body.password, config.PASSWORD):
        raise HTTPException(401, "Invalid password")
    expiry = str(int(time.time() + 28800))
    signature = hmac.new(
        config.SESSION_KEY.encode(), expiry.encode(), hashlib.sha256
    ).hexdigest()
    response.set_cookie(
        "rm_session",
        expiry + "." + signature,
        httponly=True,
        samesite="strict",
        secure=config.PUBLIC_ORIGIN.startswith("https"),
        max_age=28800,
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("rm_session")
    return {"ok": True}


@app.get("/api/status")
async def status():
    result = await trueforge.connection_status()
    with db() as c:
        dataset = c.execute("SELECT value FROM metadata WHERE key='dataset'").fetchone()
        result["dataset"] = dataset[0] if dataset else "empty"
        result["incident_count"] = c.execute(
            "SELECT COUNT(*) FROM incidents"
        ).fetchone()[0]
    result["authentication"] = "password" if config.PASSWORD else "local development"
    return result


@app.get("/api/engineers")
def engineers():
    with db() as c:
        return engineer_rows(c)


@app.patch("/api/engineers/{engineer_id}")
def update_engineer(engineer_id: str, body: EngineerUpdate):
    with db(True) as c:
        result = c.execute(
            "UPDATE engineers SET available=?,on_call=?,capacity=? WHERE id=?",
            (body.available, body.on_call, body.capacity, engineer_id),
        )
        if not result.rowcount:
            raise HTTPException(404, "Engineer not found")
        audit(
            c,
            "operator",
            "engineer.updated",
            details={"engineer_id": engineer_id, **body.model_dump()},
        )
    return {"ok": True}


@app.get("/api/tickets")
def tickets():
    with db() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT id,title,severity,team,status,created_at,updated_at FROM tickets ORDER BY created_at DESC LIMIT 200"
            )
        ]


@app.post("/api/tickets", status_code=201)
def create(body: TicketInput):
    return service.create_ticket(**body.model_dump())


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    with db() as c:
        try:
            result = ticket_row(c, ticket_id)
        except ValueError:
            raise HTTPException(404, "Ticket not found")
    result["pending_calls"] = (
        trueforge.pending_calls(result["events"])
        if result["status"] == "awaiting_approval"
        else []
    )
    return result


@app.post("/api/tickets/{ticket_id}/route", status_code=202)
async def route(ticket_id: str):
    async with locks.setdefault(ticket_id, asyncio.Lock()):
        await trueforge.start(ticket_id)
    return get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/decision")
async def decision(ticket_id: str, body: Decision):
    async with locks.setdefault(ticket_id, asyncio.Lock()):
        with db(True) as c:
            t = ticket_row(c, ticket_id)
            if t["status"] != "awaiting_approval" or t["version"] != body.version:
                raise ValueError(
                    "Recommendation changed or was already reviewed. Refresh this ticket."
                )
            pending = trueforge.pending_calls(t["events"])
            if len(pending) != 1:
                raise ValueError(
                    "Unexpected approval request. Review this run in TrueForge."
                )
            call = pending[0]
            args = call["arguments"]
            # Tool names may carry a connector namespace, but must end in the exact tool name.
            if (
                not call["name"].endswith("assign_ticket")
                or args.get("ticket_id") != ticket_id
            ):
                raise ValueError("Approval does not match this ticket assignment")
            rec = t["recommendation"]
            if (
                not rec
                or not rec.get("primary")
                or args.get("engineer_id") != rec["primary"]["id"]
            ):
                raise ValueError("Approval does not match the ranked primary engineer")
            if body.allow:
                service.grant(c, t, args["engineer_id"], "operator")
            else:
                c.execute("DELETE FROM approvals WHERE ticket_id=?", (ticket_id,))
                audit(c, "operator", "assignment.denied", ticket_id)
            c.execute(
                "UPDATE tickets SET status=?,updated_at=? WHERE id=?",
                ("approving" if body.allow else "rejected", now(), ticket_id),
            )
        await trueforge.resume(ticket_id, call, body.allow)
    return get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/resolve")
def resolve(ticket_id: str):
    return service.resolve(ticket_id, "operator")


@app.get("/api/incidents")
def incidents(q: str = ""):
    if len(q) > 200:
        raise HTTPException(422, "Search too long")
    with db() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT i.*,e.name AS resolver_name FROM incidents i JOIN engineers e ON e.id=i.resolved_by WHERE i.title LIKE ? OR i.id LIKE ? ORDER BY i.id LIMIT 200",
                ("%" + q + "%", "%" + q + "%"),
            )
        ]


@app.get("/api/audit")
def audit_log():
    with db() as c:
        return [
            dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 300")
        ]


DIST = config.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if not (DIST / "index.html").exists():
        return JSONResponse(
            {"message": "Build the frontend: cd frontend && npm ci && npm run build"},
            status_code=503,
        )
    return FileResponse(DIST / "index.html")


# Mounted last: REST and dashboard routes take precedence; the MCP endpoint is /mcp.
app.mount("/", mcp.streamable_http_app())
