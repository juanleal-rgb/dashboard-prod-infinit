import os
import logging
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import httpx
from datetime import datetime
from itsdangerous import URLSafeSerializer, BadSignature

from database import engine, get_db, Base
from models import InfinitCall
from schemas import WebhookPayload, CallResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Infinit Dashboard",
    description="Call tracking dashboard for Infinit Banking",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY", "infinit-dashboard-secret-key-change-me")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
BATCH_WEBHOOK_URL = "https://workflows.platform.happyrobot.ai/hooks/9rwfk2fvy3nm"

serializer = URLSafeSerializer(SECRET_KEY)
COOKIE_NAME = "infinit_session"


def get_session(request: Request) -> Optional[str]:
    """Return 'admin', 'user', or None based on cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        role = serializer.loads(token)
        return role
    except BadSignature:
        return None


def require_auth(request: Request) -> str:
    """Dependency: require any authenticated session."""
    role = get_session(request)
    if not role:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return role


def require_admin(request: Request) -> str:
    """Dependency: require admin session."""
    role = get_session(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role


# ==================== AUTH ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(request: Request, response: Response, password: str = Form(...)):
    if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        role = "admin"
    elif DASHBOARD_PASSWORD and password == DASHBOARD_PASSWORD:
        role = "user"
    else:
        return RedirectResponse(url="/login?error=Invalid+password", status_code=303)

    token = serializer.dumps(role)
    redirect = RedirectResponse(url="/", status_code=303)
    redirect.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    logger.info(f"🔑 Login successful as {role}")
    return redirect


@app.get("/logout")
async def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(COOKIE_NAME)
    return redirect


# ==================== DASHBOARD ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    role = get_session(request)
    if not role:
        return RedirectResponse(url="/login", status_code=303)

    calls = db.query(InfinitCall).order_by(InfinitCall.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "calls": calls, "role": role}
    )


# ==================== WEBHOOK (public — called by HappyRobot) ====================

@app.post("/api/webhook")
async def receive_webhook(payload: WebhookPayload, db: Session = Depends(get_db)):
    """Receive call result from HappyRobot workflow."""
    call = InfinitCall(
        phone=payload.phone or "",
        status=payload.status or "",
        qualified=payload.qualified or "",
        meeting=payload.meeting or "",
        summary=payload.summary or "",
        attempt=payload.attempt or "",
        duration=payload.duration or "",
        name=payload.name or "",
        company=payload.company or "",
        call_url=payload.call_url or "",
        country=payload.country or "",
        created_at=datetime.utcnow(),
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    logger.info(f"📨 Webhook received: #{call.id} - {call.name} ({call.company}) - {call.status}")
    return {"message": "ok", "id": call.id}


# ==================== ADMIN ACTIONS ====================

@app.post("/api/launch-batch")
async def launch_batch(request: Request):
    """Admin: launch a batch of calls via HappyRobot webhook."""
    role = get_session(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(BATCH_WEBHOOK_URL, json={}, timeout=30.0)
            logger.info(f"🚀 Batch launched — HappyRobot responded {resp.status_code}")
            return {"success": True, "message": "Batch launched successfully", "status_code": resp.status_code}
    except Exception as e:
        logger.error(f"❌ Batch launch failed: {str(e)}")
        return {"success": False, "message": f"Failed to launch batch: {str(e)}"}


# ==================== DATA API (authenticated) ====================

@app.get("/api/calls", response_model=List[CallResponse])
async def get_calls(
    request: Request,
    status: Optional[str] = None,
    qualified: Optional[str] = None,
    country: Optional[str] = None,
    db: Session = Depends(get_db)
):
    role = get_session(request)
    if not role:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = db.query(InfinitCall).order_by(InfinitCall.created_at.desc())
    if status:
        query = query.filter(InfinitCall.status == status)
    if qualified:
        query = query.filter(InfinitCall.qualified == qualified)
    if country:
        query = query.filter(InfinitCall.country == country)
    return query.all()


@app.delete("/api/calls/{call_id}")
async def delete_call(call_id: int, request: Request, db: Session = Depends(get_db)):
    role = get_session(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    call = db.query(InfinitCall).filter(InfinitCall.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    db.delete(call)
    db.commit()
    logger.info(f"🗑️ Call #{call_id} deleted by admin")
    return {"message": "Deleted successfully"}


@app.get("/api/statistics")
async def get_statistics(request: Request, db: Session = Depends(get_db)):
    role = get_session(request)
    if not role:
        raise HTTPException(status_code=401, detail="Unauthorized")

    total = db.query(InfinitCall).count()
    qualified_yes = db.query(InfinitCall).filter(InfinitCall.qualified == "Yes").count()
    qualified_no = db.query(InfinitCall).filter(InfinitCall.qualified == "No").count()
    meetings = db.query(InfinitCall).filter(InfinitCall.meeting != "", InfinitCall.meeting.isnot(None)).count()
    voicemails = db.query(InfinitCall).filter(InfinitCall.status == "Voicemail").count()

    # Status breakdown
    from sqlalchemy import func
    status_counts = db.query(InfinitCall.status, func.count(InfinitCall.id)).group_by(InfinitCall.status).all()
    by_status = {s: c for s, c in status_counts if s}

    country_counts = db.query(InfinitCall.country, func.count(InfinitCall.id)).group_by(InfinitCall.country).all()
    by_country = {c: n for c, n in country_counts if c}

    return {
        "total": total,
        "qualified_yes": qualified_yes,
        "qualified_no": qualified_no,
        "meetings": meetings,
        "voicemails": voicemails,
        "by_status": by_status,
        "by_country": by_country,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
