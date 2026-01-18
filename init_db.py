# C:\Project\kaist\2_week\blockpass-back\init_db.py
import asyncio
from app.core.db import engine, Base
# 모든 모델을 미리 로드해야 테이블이 생성됩니다.
from app.models.models import User, BusinessProfile, CustomerProfile, Facility, Pass, RefundPolicy, RefundPolicyRule, Order, Subscription, BlockchainContract, Refund, OCRDocument

async def init_models():
    async with engine.begin() as conn:
        print("로컬 DB에 ERD 구조를 반영 중입니다...")
        # 1. 기존 테이블 삭제 (초기화가 필요한 경우만 주석 해제)
        # await conn.run_sync(Base.metadata.drop_all)
        
        # 2. 모든 테이블 생성
        await conn.run_sync(Base.metadata.create_all)
        print("모든 테이블(OCR 포함)이 성공적으로 생성되었습니다.")

if __name__ == "__main__":
    asyncio.run(init_models())