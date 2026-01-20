# C:\Project\kaist\2_week\blockpass-back\api\orders.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.db import get_db
from api.auth import get_current_user
from app.models.models import User, Pass, Order, Subscription, Refund
from app.schemas.schemas import OrderPurchaseRequest
from datetime import datetime, timedelta

router = APIRouter(prefix="/orders", tags=["Order"])

@router.post("/purchase/{pass_id}")
async def purchase_pass(
    pass_id: int,
    payload: OrderPurchaseRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. 이용권 정보 및 가격 확인
    result = await db.execute(select(Pass).where(Pass.id == pass_id))
    target_pass = result.scalar_one_or_none()
    
    if not target_pass:
        raise HTTPException(status_code=404, detail="존재하지 않는 이용권입니다.")
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="고객만 구매할 수 있습니다.")
    if not target_pass.contract_address:
        raise HTTPException(status_code=400, detail="블록체인에 배포된 이용권이 아닙니다.")
    print(f"[purchase_pass] user_id={current_user.user_id} email={current_user.id} pass_id={pass_id}")

    try:
        now = datetime.utcnow()
        existing_subs = await db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.user_id,
                Subscription.pass_id == target_pass.id,
                Subscription.status == "active",
            )
        )
        active_sub = existing_subs.scalar_one_or_none()
        if active_sub and active_sub.end_at and active_sub.end_at > now:
            raise HTTPException(status_code=409, detail="이미 활성화된 이용권이 있습니다.")
        if active_sub and active_sub.end_at and active_sub.end_at <= now:
            active_sub.status = "expired"
        if active_sub and active_sub.end_at is None:
            raise HTTPException(status_code=409, detail="이미 활성화된 이용권이 있습니다.")

        # 2. 주문 정보 생성 (DB 저장)
        new_order = Order(
            user_id=current_user.user_id,
            pass_id=target_pass.id,
            amount=target_pass.price,
            tx_hash=payload.tx_hash if payload else None,
            chain=payload.chain if payload else target_pass.contract_chain,
            status="paid",
        )
        db.add(new_order)
        await db.flush() # order.id 확보

        start_at = now
        duration_minutes = (
            target_pass.duration_minutes
            if target_pass.duration_minutes is not None
            else (target_pass.duration_days or 0) * 24 * 60
        )
        end_at = start_at + timedelta(minutes=duration_minutes)
        # 4. 유저 구독 정보 갱신 (실제 서비스 이용권 부여)
        new_sub = Subscription(
            user_id=current_user.user_id,
            pass_id=target_pass.id,
            start_at=start_at, # 추가
            end_at=end_at,
            status="active"
        )
        db.add(new_sub)

        await db.commit()
        return {
            "status": "success",
            "order_id": new_order.id,
            "contract_address": target_pass.contract_address,
            "message": f"'{target_pass.title}' 구매 및 블록체인 등록 완료!"
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"구매 처리 중 오류: {str(e)}")
    # [C:\Project\kaist\2_week\blockpass-back\api\orders.py 맨 아래에 추가]
@router.get("/my")
async def get_my_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 내 주문, 이용권 이름, 블록체인 주소를 한 번에 가져오는 쿼리입니다.
    query = text("""
        SELECT o.id,
               o.pass_id,
               o.tx_hash,
               o.chain,
               p.title,
               p.price,
               p.duration_minutes,
               p.terms,
               p.contract_address,
               p.contract_chain,
               p.refund_rules,
               s.start_at,
               s.end_at,
               s.status
        FROM orders o
        JOIN passes p ON o.pass_id = p.id
        JOIN subscriptions s ON o.user_id = s.user_id AND o.pass_id = s.pass_id
        WHERE o.user_id = :u_id
          AND o.status != 'cancelled'
          AND s.status NOT IN ('cancelled', 'refunded')
        ORDER BY o.created_at DESC
    """)
    result = await db.execute(query, {"u_id": current_user.user_id})
    rows = []
    for row in result:
        data = dict(row._mapping)
        if isinstance(data.get("refund_rules"), str):
            try:
                import json
                data["refund_rules"] = json.loads(data["refund_rules"])
            except Exception:
                data["refund_rules"] = []
        rows.append(data)
    return rows


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")

    order.status = "cancelled"
    await db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE user_id = :u_id AND pass_id = :p_id
        """),
        {"u_id": current_user.user_id, "p_id": order.pass_id},
    )
    await db.commit()
    return {"status": "success"}


@router.post("/refund/{order_id}")
async def refund_order(
    order_id: int,
    payload: OrderPurchaseRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")

    order.status = "refunded"
    await db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'refunded'
            WHERE user_id = :u_id AND pass_id = :p_id
        """),
        {"u_id": current_user.user_id, "p_id": order.pass_id},
    )
    if payload and payload.tx_hash:
        order.tx_hash = payload.tx_hash
    if payload and payload.chain:
        order.chain = payload.chain
    db.add(Refund(order_id=order.id, refund_amount=0, reason="user_refund"))
    await db.commit()
    return {"status": "success"}


@router.post("/bankruptcy/{order_id}")
async def bankruptcy_refund(
    order_id: int,
    payload: OrderPurchaseRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")

    order.status = "refunded"
    await db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'refunded'
            WHERE user_id = :u_id AND pass_id = :p_id
        """),
        {"u_id": current_user.user_id, "p_id": order.pass_id},
    )
    if payload and payload.tx_hash:
        order.tx_hash = payload.tx_hash
    if payload and payload.chain:
        order.chain = payload.chain
    db.add(Refund(order_id=order.id, refund_amount=0, reason="bankruptcy"))
    await db.commit()
    return {"status": "success"}
