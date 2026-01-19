# C:\Project\kaist\2_week\blockpass-back\api\business.py
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.db import get_db
from api.auth import get_current_user
from app.models.models import BusinessProfile, Pass, Facility
from app.schemas.schemas import PassCreateRequest

router = APIRouter(prefix="/business", tags=["Business"])


@router.get("/passes")
async def list_business_passes(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "business":
        raise HTTPException(status_code=403, detail="사업자만 접근할 수 있습니다.")

    profile_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.user_id == current_user.user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return []

    passes_result = await db.execute(
        select(Pass).where(Pass.business_id == profile.id).order_by(Pass.created_at.desc())
    )
    passes = passes_result.scalars().all()

    return [
        {
            "id": p.id,
            "title": p.title,
            "terms": p.terms,
            "price": p.price,
            "duration_days": p.duration_days,
            "duration_minutes": p.duration_minutes,
            "contract_address": p.contract_address,
            "contract_chain": p.contract_chain,
            "refund_rules": p.refund_rules,
            "status": p.status,
            "created_at": p.created_at,
        }
        for p in passes
    ]


@router.post("/passes")
async def create_business_pass(
    payload: PassCreateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "business":
        raise HTTPException(status_code=403, detail="사업자만 접근할 수 있습니다.")

    profile_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.user_id == current_user.user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="사업자 프로필이 없습니다.")

    facility_result = await db.execute(
        select(Facility).where(Facility.business_id == profile.id).order_by(Facility.id)
    )
    facility = facility_result.scalars().first()

    new_pass = Pass(
        business_id=profile.id,
        facility_id=facility.id if facility else None,
        title=payload.title,
        terms=payload.terms,
        price=Decimal(str(payload.price)),
        duration_days=payload.duration_days,
        duration_minutes=payload.duration_minutes,
        contract_address=payload.contract_address,
        contract_chain=payload.contract_chain,
        refund_rules=[rule.model_dump() for rule in payload.refund_rules]
        if payload.refund_rules
        else None,
        status="active",
    )
    db.add(new_pass)
    await db.commit()
    await db.refresh(new_pass)

    return {
        "id": new_pass.id,
        "title": new_pass.title,
        "terms": new_pass.terms,
        "price": new_pass.price,
        "duration_days": new_pass.duration_days,
        "duration_minutes": new_pass.duration_minutes,
        "status": new_pass.status,
    }


@router.get("/members")
async def list_business_members(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "business":
        raise HTTPException(status_code=403, detail="사업자만 접근할 수 있습니다.")

    profile_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.user_id == current_user.user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return []

    rows = await db.execute(
        text(
            """
            SELECT u.user_id, u.name, u.wallet_address, p.title
            FROM subscriptions s
            JOIN passes p ON s.pass_id = p.id
            JOIN users u ON s.user_id = u.user_id
            WHERE p.business_id = :b_id
              AND s.status != 'cancelled'
            ORDER BY u.user_id, p.title
            """
        ),
        {"b_id": profile.id},
    )

    members = {}
    for row in rows:
        user_id = row.user_id
        if user_id not in members:
            members[user_id] = {
                "user_id": user_id,
                "name": row.name,
                "wallet_address": row.wallet_address,
                "passes": [],
            }
        members[user_id]["passes"].append(row.title)

    return list(members.values())
