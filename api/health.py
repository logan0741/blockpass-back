from fastapi import APIRouter
from sqlalchemy import text

from api.db import engine

router = APIRouter()


@router.get("/")
def read_root() -> dict:
    return {"status": "ok"}


@router.get("/db/health")
def db_health() -> dict:
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()
    return {"db_ok": value == 1}
