import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./physis_tester.db")

# PostgreSQL requires different connect args than SQLite.
# pool_pre_ping: SQLAlchemy tests every checked-out connection with a
#   lightweight SELECT 1 before handing it to the caller, and silently
#   reconnects if the connection is dead. Eliminates PendingRollbackError
#   when Supabase / Render drops idle connections mid-build.
# pool_recycle: proactively close and replace any connection older than
#   300 seconds so we retire them before Supabase's idle timeout hits.
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
