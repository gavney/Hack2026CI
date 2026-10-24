import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.database import engine, Base
import backend.models  # noqa
from backend.routers import (
    auth, companies, operations, forecast, events, scenarios, integrations, analytics, counterparties
)

# Auto-create newly added tables
Base.metadata.create_all(bind=engine)

def seed_existing_user_companies():
    from backend.database import SessionLocal
    from backend.models import User, UserCompany
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for u in users:
            if u.company_id:
                exists = db.query(UserCompany).filter(
                    UserCompany.user_id == u.id,
                    UserCompany.company_id == u.company_id
                ).first()
                if not exists:
                    uc = UserCompany(
                        user_id=u.id,
                        company_id=u.company_id,
                        role=u.role or "owner",
                        is_default=True
                    )
                    db.add(uc)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

seed_existing_user_companies()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Интеллектуальный сервис финансового прогнозирования и предотвращения кассовых разрывов для клиентов Банка «Центр-Инвест»",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for local development and hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers under /api
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(companies.router, prefix=settings.API_PREFIX)
app.include_router(operations.router, prefix=settings.API_PREFIX)
app.include_router(forecast.router, prefix=settings.API_PREFIX)
app.include_router(events.router, prefix=settings.API_PREFIX)
app.include_router(scenarios.router, prefix=settings.API_PREFIX)
app.include_router(integrations.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(counterparties.router, prefix=settings.API_PREFIX)

# Serve Frontend static assets
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/health")
def health_check():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "model_version": "stub-0.1",
        "integrations_status": {
            "1c": "mock_ready",
            "fns": "mock_ready",
            "bank_centroinvest": "active",
            "edo": "mock_ready",
            "marketplaces": "mock_ready"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
