from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import io
import csv

from roast_engine import generate_roast, ROAST_LEVELS


# ---------- env ----------
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']
JWT_SECRET = os.environ['JWT_SECRET']
ADMIN_EMAIL = os.environ['ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
JWT_ALGO = "HS256"

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

app = FastAPI(title="Roast My Startup API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("roast")


# ---------- auth helpers ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(email: str) -> str:
    payload = {
        "sub": email,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def require_admin(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        if payload.get("type") != "access" or payload.get("role") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.admins.find_one({"email": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Admin not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------- models ----------

class StartupInput(BaseModel):
    startup_name: str
    startup_description: str
    industry: str
    startup_website: Optional[str] = None
    startup_stage: Optional[str] = None
    monthly_revenue: Optional[str] = None
    roast_level: str = "reality"


class RoastResponse(BaseModel):
    roast_id: str
    score: int
    score_category: str
    level: str
    level_label: str
    dna: dict
    archetype: dict
    roast: dict
    what_works: List[str]
    what_needs_work: List[str]
    investor_reaction: str
    reality_check: str
    high_impact_improvement: str
    best_line: str


class LeadSubmit(BaseModel):
    roast_id: str
    full_name: str
    email: EmailStr
    contact_number: str
    linkedin_url: Optional[str] = None
    startup_website: Optional[str] = None
    biggest_challenge: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


# ---------- helpers ----------

def calc_priority(*, website: Optional[str], linkedin: Optional[str], description: str) -> str:
    has_site = bool(website and website.strip())
    has_li = bool(linkedin and linkedin.strip())
    detailed = len(description.strip()) >= 80
    if has_site and has_li and detailed:
        return "HIGH"
    if (has_site or has_li) and detailed:
        return "MEDIUM"
    if has_site or has_li or detailed:
        return "MEDIUM"
    return "LOW"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- public endpoints ----------

@api.get("/")
async def root():
    return {"status": "ok", "service": "Roast My Startup"}


@api.get("/roast-levels")
async def get_roast_levels():
    return [{"key": k, **v} for k, v in ROAST_LEVELS.items()]


@api.post("/roast", response_model=RoastResponse)
async def create_roast(payload: StartupInput):
    if not payload.startup_name.strip() or not payload.startup_description.strip() or not payload.industry.strip():
        raise HTTPException(status_code=400, detail="startup_name, startup_description and industry are required")
    if payload.roast_level not in ROAST_LEVELS:
        raise HTTPException(status_code=400, detail="Invalid roast_level")

    result = generate_roast(
        startup_name=payload.startup_name,
        description=payload.startup_description,
        industry=payload.industry,
        website=payload.startup_website,
        stage=payload.startup_stage,
        monthly_revenue=payload.monthly_revenue,
        level=payload.roast_level,
    )
    roast_id = str(uuid.uuid4())

    doc = {
        "roast_id": roast_id,
        "created_at": now_iso(),
        "startup_name": payload.startup_name.strip(),
        "startup_description": payload.startup_description.strip(),
        "industry": payload.industry.strip(),
        "startup_website": (payload.startup_website or "").strip() or None,
        "startup_stage": payload.startup_stage,
        "monthly_revenue": payload.monthly_revenue,
        "roast_level": payload.roast_level,
        "startup_score": result["score"],
        "result": result,
        "lead_captured": False,
    }
    await db.roasts.insert_one(doc)

    return RoastResponse(roast_id=roast_id, **result)


@api.post("/leads")
async def submit_lead(payload: LeadSubmit):
    if not payload.full_name.strip() or not payload.contact_number.strip() or not payload.biggest_challenge.strip():
        raise HTTPException(status_code=400, detail="full_name, contact_number and biggest_challenge are required")

    roast = await db.roasts.find_one({"roast_id": payload.roast_id}, {"_id": 0})
    if not roast:
        raise HTTPException(status_code=404, detail="Roast not found")

    priority = calc_priority(
        website=payload.startup_website or roast.get("startup_website"),
        linkedin=payload.linkedin_url,
        description=roast.get("startup_description", ""),
    )

    lead_doc = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "full_name": payload.full_name.strip(),
        "email": payload.email.lower().strip(),
        "contact_number": payload.contact_number.strip(),
        "linkedin_url": (payload.linkedin_url or "").strip() or None,
        "startup_name": roast["startup_name"],
        "startup_description": roast["startup_description"],
        "startup_website": (payload.startup_website or roast.get("startup_website") or "").strip() or None,
        "industry": roast["industry"],
        "startup_stage": roast.get("startup_stage"),
        "monthly_revenue": roast.get("monthly_revenue"),
        "biggest_challenge": payload.biggest_challenge,
        "startup_score": roast["startup_score"],
        "roast_level": roast["roast_level"],
        "lead_priority": priority,
        "roast_id": payload.roast_id,
    }
    await db.leads.insert_one(lead_doc)
    await db.roasts.update_one({"roast_id": payload.roast_id}, {"$set": {"lead_captured": True}})

    return {"ok": True, "lead_priority": priority}


@api.get("/roast/{roast_id}")
async def get_roast(roast_id: str):
    """Return full roast — only if lead has been captured for this roast."""
    roast = await db.roasts.find_one({"roast_id": roast_id}, {"_id": 0})
    if not roast:
        raise HTTPException(status_code=404, detail="Roast not found")
    if not roast.get("lead_captured"):
        raise HTTPException(status_code=403, detail="Lead capture required")
    r = roast["result"]
    return {
        "roast_id": roast_id,
        "startup_name": roast["startup_name"],
        **r,
    }


@api.get("/example-roasts")
async def example_roasts():
    examples = [
        {"startup": "AI-Powered Dog Dating App", "industry": "Pet Tech",
         "line": "Your startup solves a problem nobody knew existed and most dogs still don't.", "score": 38, "archetype": "The Dream Seller"},
        {"startup": "Uber for Houseplants", "industry": "Marketplace",
         "line": "You've digitized a service that was already efficient: walking 10 feet to a nursery.", "score": 44, "archetype": "The Buzzword Collector"},
        {"startup": "Notion but for Toddlers", "industry": "Productivity",
         "line": "Your TAM is real, your ICP eats crayons, and your churn is measured in nap cycles.", "score": 52, "archetype": "The Visionary"},
        {"startup": "Blockchain-based Resume Verification", "industry": "HR Tech",
         "line": "You've added 17 confirmations to a problem that was solved by LinkedIn in 2009.", "score": 35, "archetype": "The Buzzword Collector"},
        {"startup": "AI Therapist for Founders", "industry": "Mental Health",
         "line": "Your TAM is enormous. So is your liability surface. Read both before you raise.", "score": 67, "archetype": "The Market Whisperer"},
        {"startup": "Slack for Solo Founders", "industry": "SaaS",
         "line": "You've built a multiplayer tool for one player. The bug is also the feature.", "score": 41, "archetype": "The Product Addict"},
    ]
    return examples


# ---------- admin ----------

@api.post("/auth/login")
async def admin_login(body: LoginInput):
    email = body.email.lower().strip()
    user = await db.admins.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(email)
    return {"access_token": token, "token_type": "bearer", "email": email}


@api.get("/auth/me")
async def me(user=Depends(require_admin)):
    return user


@api.get("/admin/leads")
async def list_leads(
    user=Depends(require_admin),
    q: Optional[str] = None,
    priority: Optional[str] = None,
    challenge: Optional[str] = None,
    roast_level: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|startup_score|full_name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = 200,
):
    filt = {}
    if q:
        rx = {"$regex": q, "$options": "i"}
        filt["$or"] = [
            {"full_name": rx}, {"email": rx}, {"contact_number": rx}, {"startup_name": rx},
            {"industry": rx}, {"biggest_challenge": rx},
        ]
    if priority:
        filt["lead_priority"] = priority.upper()
    if challenge:
        filt["biggest_challenge"] = challenge
    if roast_level:
        filt["roast_level"] = roast_level

    direction = -1 if order == "desc" else 1
    cursor = db.leads.find(filt, {"_id": 0}).sort(sort_by, direction).limit(limit)
    leads = await cursor.to_list(length=limit)
    total = await db.leads.count_documents(filt)
    return {"leads": leads, "total": total}


@api.get("/admin/stats")
async def admin_stats(user=Depends(require_admin)):
    total_leads = await db.leads.count_documents({})
    total_roasts = await db.roasts.count_documents({})
    high = await db.leads.count_documents({"lead_priority": "HIGH"})
    med = await db.leads.count_documents({"lead_priority": "MEDIUM"})
    low = await db.leads.count_documents({"lead_priority": "LOW"})

    # average score
    pipeline = [{"$group": {"_id": None, "avg": {"$avg": "$startup_score"}}}]
    avg_doc = await db.leads.aggregate(pipeline).to_list(1)
    avg_score = round(avg_doc[0]["avg"], 1) if avg_doc else 0

    return {
        "total_leads": total_leads,
        "total_roasts": total_roasts,
        "high_priority": high,
        "medium_priority": med,
        "low_priority": low,
        "avg_score": avg_score,
    }


@api.get("/admin/leads/export")
async def export_leads(user=Depends(require_admin)):
    cursor = db.leads.find({}, {"_id": 0}).sort("created_at", -1)
    leads = await cursor.to_list(length=10000)

    buf = io.StringIO()
    fieldnames = [
        "created_at", "full_name", "email", "contact_number", "linkedin_url", "startup_name",
        "startup_description", "startup_website", "industry", "startup_stage",
        "monthly_revenue", "biggest_challenge", "startup_score", "roast_level",
        "lead_priority",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for l in leads:
        writer.writerow(l)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=roast_leads.csv"},
    )


# ---------- startup ----------

@app.on_event("startup")
async def on_startup():
    # indexes
    await db.leads.create_index("created_at")
    await db.leads.create_index("email")
    await db.roasts.create_index("roast_id", unique=True)
    await db.admins.create_index("email", unique=True)

    # seed admin (idempotent)
    existing = await db.admins.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.admins.insert_one({
            "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "role": "admin",
            "created_at": now_iso(),
        })
        logger.info("Seeded admin user: %s", ADMIN_EMAIL)
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.admins.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )
        logger.info("Updated admin password for: %s", ADMIN_EMAIL)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
