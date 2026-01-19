# C:\Project\kaist\2_week\blockpass-back\api\facilities.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.db import get_db
from app.models.models import Facility, Pass, User, BusinessProfile

router = APIRouter(prefix="/facilities", tags=["Facility"])

# 1. 테스트용 데이터 생성 (허점 1 해결)
@router.post("/seed")
async def seed_facilities(db: AsyncSession = Depends(get_db)):
    # 이미 데이터가 있는지 확인
    check = await db.execute(select(Facility))
    if check.scalars().first():
        return {"message": "이미 데이터가 존재합니다."}
    biz_result = await db.execute(select(BusinessProfile))
    biz_profile = biz_result.scalars().first()
    target_id = biz_profile.id if biz_profile else 1
    # 테스트 사장님 계정 ID (user_id=1 가정)
    test_facility = Facility(
        business_id=target_id, # business_id=1 대신 target_id 사용
        name="블록패스 짐 (대전점)",
        category="gym",
        address="대전광역시 유성구 대학로 291",
        lat=36.366,
        lng=127.344
    )
    db.add(test_facility)
    await db.flush()

    # 이용권 추가
    test_pass = Pass(
        business_id=target_id,
        facility_id=test_facility.id,
        title="1개월 자유 이용권",
        price=100000,
        duration_days=30,
        duration_minutes=30 * 24 * 60
    )
    db.add(test_pass)
    await db.commit()
    return {"status": "success", "message": "테스트 데이터 생성 완료"}

# 2. 시설 및 최저가 목록 조회 (허점 2 해결)
# [api/facilities.py] get_facilities 함수 전체를 아래 내용으로 교체하세요.
@router.get("/list")
async def get_facilities(db: AsyncSession = Depends(get_db)):
    # ONLY_FULL_GROUP_BY 호환: 시설별 최저가 이용권 1건을 서브쿼리로 선택
    query = text("""
        SELECT
            f.id,
            f.business_id,
            f.name,
            f.category,
            f.address,
            f.lat,
            f.lng,
            f.created_at,
            p.price as min_price,
            p.id as min_pass_id
        FROM facilities f
        LEFT JOIN passes p
          ON p.id = (
            SELECT p2.id
            FROM passes p2
            WHERE p2.facility_id = f.id
            ORDER BY p2.price ASC, p2.id ASC
            LIMIT 1
          )
    """)
    result = await db.execute(query)
    
    # [수정] App.jsx의 요구사항인 "ETH" 표시를 위해 데이터를 가공하여 반환
    return [
        {
            **dict(row._mapping),
            "price_display": f"{row.min_price:.4f} ETH" if row.min_price else "가격 준비중"
        } 
        for row in result
    ]


@router.get("/{facility_id}/passes")
async def get_passes_by_facility(
    facility_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Pass).where(Pass.facility_id == facility_id).order_by(Pass.created_at.desc())
    )
    passes = result.scalars().all()
    items = []
    for p in passes:
        rules = p.refund_rules
        if isinstance(rules, str):
            try:
                import json
                rules = json.loads(rules)
            except Exception:
                rules = []
        items.append(
            {
                "id": p.id,
                "title": p.title,
                "price": p.price,
                "duration_days": p.duration_days,
                "duration_minutes": p.duration_minutes,
                "terms": p.terms,
                "contract_address": p.contract_address,
                "contract_chain": p.contract_chain,
                "refund_rules": rules,
                "status": p.status,
            }
        )
    return items
