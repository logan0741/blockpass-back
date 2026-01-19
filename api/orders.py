# C:\Project\kaist\2_week\blockpass-back\api\orders.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.db import get_db
from api.auth import get_current_user
from app.models.models import User, Pass, Order, BlockchainContract, Subscription
import uuid
from datetime import datetime, timedelta # 날짜 계산을 위해 추가

router = APIRouter(prefix="/orders", tags=["Order"])

@router.post("/purchase/{pass_id}")
async def purchase_pass(
    pass_id: int,
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

    try:
        # 2. 주문 정보 생성 (DB 저장)
        new_order = Order(
            user_id=current_user.user_id,
            pass_id=target_pass.id,
            amount=target_pass.price,
            status="paid"
        )
        db.add(new_order)
        await db.flush() # order.id 확보

        # 3. 블록체인 계약 생성 (Mocking: 실제로는 여기서 스마트 컨트랙트 배포)
        # [허점 2 해결] DB와 블록체인 정보를 한 번에 묶어 저장
        mock_contract_address = f"0x{uuid.uuid4().hex[:40]}" # 가짜 지갑 주소 생성
        new_contract = BlockchainContract(
            order_id=new_order.id,
            contract_address=mock_contract_address,
            chain="Polygon",
            status="deployed"
        )
        db.add(new_contract)
        start_at = datetime.utcnow()
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
            "contract_address": mock_contract_address,
            "message": f"'{target_pass.title}' 구매 및 블록체인 등록 완료!"
        }

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
        SELECT o.id, p.title, p.price, p.duration_minutes, bc.contract_address, s.start_at, s.end_at, s.status
        FROM orders o
        JOIN passes p ON o.pass_id = p.id
        JOIN blockchain_contracts bc ON o.id = bc.order_id
        JOIN subscriptions s ON o.user_id = s.user_id AND o.pass_id = s.pass_id
        WHERE o.user_id = :u_id
          AND o.status != 'cancelled'
          AND s.status != 'cancelled'
        ORDER BY o.created_at DESC
    """)
    result = await db.execute(query, {"u_id": current_user.user_id})
    return [dict(row._mapping) for row in result]


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
