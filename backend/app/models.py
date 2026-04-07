from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # e.g. "health", "finance", "productivity"
    complexity = Column(String, nullable=False)  # "simple", "medium", "complex"
    source = Column(String, default="seed")  # "seed" or "ai_generated"
    created_at = Column(DateTime, default=datetime.utcnow)
    runs = relationship("Run", back_populates="scenario")

class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")  # pending, running, completed, failed
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
    description = Column(Text)  # the actual input sent to Physis
    status = Column(String, default="pending")  # pending, running, passed, failed, error
    build_time_seconds = Column(Float, nullable=True)
    live_url = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    physis_response = Column(Text, nullable=True)  # raw JSON response stored as string
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    batch = relationship("Batch", back_populates="runs")
    scenario = relationship("Scenario", back_populates="runs")
