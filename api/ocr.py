# C:\Project\kaist\2_week\blockpass-back\api\ocr.py
import json
import os
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.core.db import get_db
from api.auth import get_current_user
from app.models.models import User, BusinessProfile, CustomerProfile
from fastapi.responses import Response
from fastapi import BackgroundTasks # 추가

load_dotenv()

router = APIRouter(prefix="/ocr", tags=["ocr"])

AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://172.10.5.70:8123")
AI_API_KEY = os.getenv("AI_API_KEY")
BACK_API_KEY = os.getenv("BACK_API_KEY")
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "10485760"))

def require_api_key(expected_key: str | None, received_key: str | None) -> None:
    if not expected_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if received_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
async def send_to_ai_server(document_id: int, image_bytes: bytes, role: str, profile_id: int, db_session: AsyncSession):
    """
    사용자는 이미 응답을 받은 상태에서, 백그라운드에서 AI 서버와 통신합니다.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{AI_SERVER_URL}/ai/ocr",
                headers={"X-API-KEY": AI_API_KEY},
                files={"image": ("image.png", image_bytes, "image/png")},
                data={
                    "document_id": str(document_id),
                    "role": role,
                    "profile_id": str(profile_id),
                },
                timeout=60.0 # AI 처리는 시간이 걸릴 수 있으므로 넉넉히 설정
            )
            
            if response.status_code != 200:
                print(f"AI Server Error: {response.status_code}")
                # 실패 시 DB 업데이트 (필요 시 별도 세션 생성 권장)
                await db_session.execute(text("UPDATE ocr_documents SET status='failed' WHERE id=:id"), {"id": document_id})
                await db_session.commit()
                
        except Exception as exc:
            print(f"Background AI Request Failed: {exc}")
            try:
                await db_session.execute(text("UPDATE ocr_documents SET status='failed' WHERE id=:id"), {"id": document_id})
                await db_session.commit()
            except:
                pass
@router.post("/request")
async def ocr_request(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    # 1. 로그인 유저의 프로필 ID 조회 (허점 1 해결: .id로 수정)
    if current_user.role == "business":
        result = await db.execute(select(BusinessProfile.id).where(BusinessProfile.user_id == current_user.user_id))
        profile_id = result.scalar_one_or_none()
        customer_profile_id, business_profile_id = None, profile_id
    else:
        result = await db.execute(select(CustomerProfile.id).where(CustomerProfile.user_id == current_user.user_id))
        profile_id = result.scalar_one_or_none()
        customer_profile_id, business_profile_id = profile_id, None

    if not profile_id:
        raise HTTPException(status_code=404, detail="프로필 정보를 찾을 수 없습니다.")

    # 2. 이미지 크기 검증
    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="이미지 용량이 너무 큽니다.")

    # 3. DB에 OCR 요청 기록 저장
    try:
        query = text("""
            INSERT INTO ocr_documents (
                customer_profile_id, business_profile_id, image_png, status
            ) VALUES (
                :c_id, :b_id, :img, 'pending'
            )
        """)
        
        result = await db.execute(query, {
            "c_id": customer_profile_id,
            "b_id": business_profile_id,
            "img": image_bytes
        })
        
        # [허점 3 보완] ID를 먼저 확보하고 마지막에 한 번만 커밋
        document_id = result.lastrowid 
        if not document_id:
            res = await db.execute(text("SELECT LAST_INSERT_ID()"))
            document_id = res.scalar()
            
        await db.commit() 
        
    except Exception as e:
        await db.rollback()
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=f"DB 저장 오류: {str(e)}")

    # 4. AI 서버 요청 로직
    if not AI_API_KEY:
         return {"document_id": document_id, "status": "saved_only", "message": "AI 키 미설정"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{AI_SERVER_URL}/ai/ocr",
                headers={"X-API-KEY": AI_API_KEY},
                files={"image": ("image.png", image_bytes, "image/png")},
                data={
                    "document_id": str(document_id),
                    "role": current_user.role,
                    "profile_id": str(profile_id),
                },
                timeout=30.0 
            )
            if response.status_code != 200:
                raise Exception(f"AI Server Error: {response.status_code}")
                
        except Exception as exc:
            update_query = text("UPDATE ocr_documents SET status='failed' WHERE id=:id")
            await db.execute(update_query, {"id": document_id})
            await db.commit()
            return {"document_id": document_id, "status": "failed", "error": str(exc)}

    return {"document_id": document_id, "status": "sent"}

# 목록 조회 API (허점 2 해결: SQL 내 컬럼명을 id로 수정)
@router.get("/list")
async def get_ocr_list(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    profile_col = "business_profile_id" if current_user.role == "business" else "customer_profile_id"
    
    # 모델에 맞게 SELECT 하위 쿼리 컬럼명을 id로 수정
    query = text(f"""
        SELECT id, status, created_at, ocr_result 
        FROM ocr_documents 
        WHERE {profile_col} = (
            SELECT id 
            FROM {"business_profiles" if current_user.role == "business" else "customer_profiles"}
            WHERE user_id = :u_id
        )
        ORDER BY created_at DESC
    """)
    
    result = await db.execute(query, {"u_id": current_user.user_id})
    return [dict(row._mapping) for row in result]

@router.get("/image/{doc_id}")
async def get_ocr_image(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = text("SELECT image_png FROM ocr_documents WHERE id = :id")
    result = await db.execute(query, {"id": doc_id})
    image_data = result.scalar()
    
    if not image_data:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
        
    return Response(content=image_data, media_type="image/png")
# C:\Project\kaist\2_week\blockpass-back\api\ocr.py 하단 추가

@router.get("/result/{doc_id}")
async def get_ocr_result_detail(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # [팩트체크] 내 것만 볼 수 있도록 보안 필터링 적용
    query = text("""
        SELECT ocr_result, status, created_at 
        FROM ocr_documents 
        WHERE id = :id AND (customer_profile_id = (SELECT id FROM customer_profiles WHERE user_id = :u_id)
        OR business_profile_id = (SELECT id FROM business_profiles WHERE user_id = :u_id))
    """)
    result = await db.execute(query, {"id": doc_id, "u_id": current_user.user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없거나 권한이 없습니다.")

    return {
        "id": doc_id,
        "status": row.status,
        "created_at": row.created_at,
        "parsed_data": row.ocr_result # AI가 채워준 JSON 데이터
    }