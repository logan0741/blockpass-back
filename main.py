import os

from fastapi import FastAPI
from sqlalchemy import create_engine, text
import uvicorn

app = FastAPI()

DB_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://user:password@127.0.0.1:3306/blockpass",
)
engine = create_engine(DB_URL, pool_pre_ping=True)


@app.get("/")
def read_root() -> dict:
    return {"status": "ok"}


@app.get("/db/health")
def db_health() -> dict:
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()
    return {"db_ok": value == 1}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
