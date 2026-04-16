import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routes import scenarios, simulator, runs, analytics, orchestrator, products
from .routes.mary import router as mary_router
from .routes.ecosystem import router as ecosystem_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Physis Tester", version="1.0.0")

allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://physis-tester.pages.dev",
    os.getenv("FRONTEND_URL", ""),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in allowed_origins if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios.router)
app.include_router(simulator.router)
app.include_router(runs.router)
app.include_router(analytics.router)
app.include_router(orchestrator.router)
app.include_router(products.router)
app.include_router(mary_router)
app.include_router(ecosystem_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "Physis Tester"}
