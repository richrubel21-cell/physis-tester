from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    complexity = Column(String, nullable=False)
    source = Column(String, default="seed")
    created_at = Column(DateTime, default=datetime.utcnow)
    runs = relationship("Run", back_populates="scenario")


class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")
    total = Column(Integer, default=0)
    completed = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    runs = relationship("Run", back_populates="batch")


class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)
    description = Column(Text)
    status = Column(String, default="pending")
    build_time_seconds = Column(Float, nullable=True)
    live_url = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    physis_response = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    batch = relationship("Batch", back_populates="runs")
    scenario = relationship("Scenario", back_populates="runs")


# ---------------------------------------------------------------------------
# Mary Tables
# ---------------------------------------------------------------------------

class MaryBatch(Base):
    __tablename__ = "mary_batches"
    id            = Column(Integer, primary_key=True, index=True)
    status        = Column(String, default="pending")   # pending, running, completed, failed
    total         = Column(Integer, default=0)
    completed     = Column(Integer, default=0)
    passed        = Column(Integer, default=0)
    failed        = Column(Integer, default=0)
    pass_rate     = Column(Float, default=0.0)
    use_ai        = Column(Boolean, default=True)
    started_at    = Column(DateTime, default=datetime.utcnow)
    finished_at   = Column(DateTime, nullable=True)
    runs          = relationship("MaryRun", back_populates="batch")


class MaryRun(Base):
    __tablename__ = "mary_runs"
    id                     = Column(Integer, primary_key=True, index=True)
    batch_id               = Column(Integer, ForeignKey("mary_batches.id"), nullable=False)
    screen                 = Column(String, nullable=False)
    prompt                 = Column(Text, nullable=False)
    prompt_type            = Column(String, default="general")   # "specific" | "general"
    source                 = Column(String, default="seed")      # "seed" | "ai_generated"
    response_text          = Column(Text, nullable=True)
    status                 = Column(String, default="pending")   # pending, passed, failed, error

    # Scoring criteria
    responded_ok           = Column(Boolean, default=False)
    speakable_ok           = Column(Boolean, default=False)
    context_ok             = Column(Boolean, default=False)
    persona_ok             = Column(Boolean, default=False)
    length_ok              = Column(Boolean, default=False)
    helpful_ok             = Column(Boolean, default=False)
    tone_ok                = Column(Boolean, default=False)
    score                  = Column(Integer, default=0)   # 0-7
    overall_pass           = Column(Boolean, default=False)

    error_message          = Column(Text, nullable=True)
    response_time_seconds  = Column(Float, nullable=True)
    started_at             = Column(DateTime, default=datetime.utcnow)
    finished_at            = Column(DateTime, nullable=True)
    batch                  = relationship("MaryBatch", back_populates="runs")


# ---------------------------------------------------------------------------
# Ecosystem Tester tables
# ---------------------------------------------------------------------------

class EcosystemBatch(Base):
    __tablename__ = "ecosystem_batches"
    id                   = Column(Integer, primary_key=True, index=True)
    type                 = Column(String, nullable=False)            # "full" | "sequential"
    status               = Column(String, default="pending")         # pending, running, completed, failed
    scenario_count       = Column(Integer, default=0)
    app_count            = Column(Integer, default=3)                # 3 or 7 — batch-wide
    pass_count           = Column(Integer, default=0)
    fail_count           = Column(Integer, default=0)
    pass_rate            = Column(Float, default=0.0)
    avg_build_time       = Column(Float, nullable=True)
    started_at           = Column(DateTime, default=datetime.utcnow)
    completed_at         = Column(DateTime, nullable=True)
    marketplace_eligible = Column(Boolean, default=False)
    runs                 = relationship("EcosystemRun", back_populates="batch")


class EcosystemRun(Base):
    __tablename__ = "ecosystem_runs"
    id                    = Column(Integer, primary_key=True, index=True)
    batch_id              = Column(Integer, ForeignKey("ecosystem_batches.id"), nullable=False)
    business_description  = Column(Text, nullable=False)
    app_count             = Column(Integer, default=3)           # 3 or 7
    type                  = Column(String, nullable=False)       # "full" | "sequential"
    status                = Column(String, default="pending")    # pending, running, passed, failed, error
    apps_planned          = Column(Integer, default=0)
    apps_built            = Column(Integer, default=0)
    apps_deployed         = Column(Integer, default=0)
    apps_integrated       = Column(Integer, default=0)
    # "passed" not "pass" — pass is a Python keyword AND reserved in several
    # SQL dialects. Keeping it as a plain boolean flag.
    passed                = Column(Boolean, default=False)
    fail_reason           = Column(Text, nullable=True)
    total_time_seconds    = Column(Float, nullable=True)
    app_urls              = Column(Text, nullable=True)          # JSON array string
    apps_detail           = Column(Text, nullable=True)          # JSON array of per-app dicts
    apps_planned_json     = Column(Text, nullable=True)          # Raw plan returned by /api/ecosystem-builder/plan
    error_message         = Column(Text, nullable=True)
    # Integration test results — 8 tests (22–29) that run AFTER every app has
    # deployed. Stored as an array of {test_id, name, passed, score, detail}
    # dicts in integration_results, with the 0–8 roll-up in integration_score.
    integration_score     = Column(Integer, default=0)
    integration_passed    = Column(Boolean, default=False)
    integration_results   = Column(Text, nullable=True)           # JSON array of per-test dicts
    integration_details   = Column(Text, nullable=True)           # Short human summary
    # Only true when every app passed its individual tests AND integration_score == 8
    marketplace_eligible  = Column(Boolean, default=False)
    created_at            = Column(DateTime, default=datetime.utcnow)
    completed_at          = Column(DateTime, nullable=True)
    batch                 = relationship("EcosystemBatch", back_populates="runs")
