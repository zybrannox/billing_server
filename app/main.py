from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.database import engine, Base, SessionLocal
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import select
from passlib.hash import bcrypt
from app.users import user_router
from app.projects import project_router
from app.project_files import file_router
from app.project_files.retention import purge_stale_originals
from app.auth import auth_router
from app.invoices import invoice_router
from app.customers import customer_router
from app.list_options import list_option_router
from app.dashboard import dashboard_router
from app.middleware import RequestSizeLimitMiddleware
from app.entities import User, UserRole
import app.entities


app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "https://workspace.zybrannox.com"],  # frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Disposition"],  # so the frontend can read download size/filename
)

# Add request size limit middleware for large file uploads (2GB max)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_upload_size=2 * 1024 * 1024 * 1024  # 2GB
)

# Compress JSON/text responses (project & employee lists, etc.) for faster loads in production
app.add_middleware(GZipMiddleware, minimum_size=1024)

# App startup event - async DB check
@app.on_event("startup")
async def startup_db_check():
    try:
        if isinstance(engine, AsyncEngine):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            Base.metadata.create_all(bind=engine)
        print("✅ Database connected and tables created successfully!")
    except Exception as e:
        print("❌ Database connection failed:", e)
        return

    seed_default_admin()
    start_retention_scheduler()


retention_scheduler: AsyncIOScheduler | None = None


def run_retention_job():
    """Opens its own DB session - this runs on the scheduler's own thread,
    independent of any request, so it can't reuse a request-scoped session
    from Depends(get_db) the way the route handlers do."""
    db = SessionLocal()
    try:
        result = purge_stale_originals(db)
        print(f"🗑️  Weekly file retention: {result}")
    except Exception as e:
        print("❌ Retention job failed:", e)
    finally:
        db.close()


def start_retention_scheduler():
    """Runs the storage-retention job (app/project_files/retention.py) on a
    fixed weekly schedule - every Sunday at 03:00 server time, a low-traffic
    window - rather than N days after whenever the server last happened to
    restart, which would drift with every deploy."""
    global retention_scheduler
    retention_scheduler = AsyncIOScheduler()
    retention_scheduler.add_job(
        run_retention_job,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="weekly_file_retention",
        replace_existing=True,
    )
    retention_scheduler.start()
    print("🗓️  File retention scheduler started (weekly, Sun 03:00).")


@app.on_event("shutdown")
async def stop_retention_scheduler():
    if retention_scheduler is not None:
        retention_scheduler.shutdown(wait=False)


def seed_default_admin():
    db = SessionLocal()
    try:
        exists = db.execute(
            select(User).where(User.username == "zybrannox")
        ).scalar_one_or_none()

        if exists:
            return

        admin = User(
            username="zybrannox",
            email="zybrannox@gmail.com",
            phone="0000000000",
            hashed_password=bcrypt.hash("admin123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("✅ Default admin user 'zybrannox' created.")
    except Exception as e:
        db.rollback()
        print("❌ Failed to seed default admin user:", e)
    finally:
        db.close()

app.include_router(user_router)
app.include_router(project_router)
app.include_router(file_router)
app.include_router(auth_router)
app.include_router(invoice_router)
app.include_router(customer_router)
app.include_router(list_option_router)
app.include_router(dashboard_router)


@app.get("/")
def read_root():
    return {"message": "FastAPI is running"}
