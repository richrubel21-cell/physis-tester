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
