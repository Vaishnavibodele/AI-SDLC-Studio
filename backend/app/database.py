import os
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sdlc_studio.db")

# For SQLite, we need to allow multithreading access
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Shared SQLite Checkpointer for LangGraph ---
# We store checkpointer in a separate SQLite database file to avoid table locking issues with uvicorn reload
checkpoint_db_path = "sdlc_checkpoints.db"
checkpoint_conn = sqlite3.connect(checkpoint_db_path, check_same_thread=False)
sqlite_checkpointer = SqliteSaver(checkpoint_conn)
