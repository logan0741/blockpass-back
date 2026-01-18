# C:\Project\kaist\2_week\blockpass-back\api\health.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 새로운 위치에서 engine과 get_db를 가져옵니다
from app.core.db import get_db

router = APIRouter()

@router.get("/")
async def read_root() -> dict:
    return {"status": "ok"}

@router.get("/db/health")
async def db_health(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        # 비동기 세션을 사용하여 쿼리 실행
        result = await db.execute(text("SELECT 1"))
        value = result.scalar()
        return {"db_ok": value == 1}
    except Exception as e:
        return {"db_ok": False, "error": str(e)}