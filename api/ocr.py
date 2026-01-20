# C:\Project\kaist\2_week\blockpass-back\api\ocr.py
import json
import os
import httpx
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Any, Dict, List
from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.core.db import get_db
from api.auth import get_current_user
from app.models.models import User, BusinessProfile, CustomerProfile, OCRDocument, Pass, Order, Subscription
from fastapi.responses import Response

load_dotenv()

router = APIRouter(prefix="/ocr", tags=["ocr"])

AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://172.10.5.70:8000")
AI_API_KEY = os.getenv("AI_API_KEY")
BACK_API_KEY = os.getenv("BACK_API_KEY")
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "10485760"))
DEFAULT_COMPANY_TYPE = os.getenv("OCR_COMPANY_TYPE", "gym")


class OcrContractRequest(BaseModel):
    document_id: int
    start_at: Optional[datetime] = None
    title: Optional[str] = None
    amount_krw: Optional[int] = None
    duration_days: Optional[int] = None


def _parse_json_maybe(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_terms(payload: Dict[str, Any]) -> Optional[str]:
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    if sections.get("terms"):
        return sections.get("terms")
    if sections.get("period"):
        return sections.get("period")
    full_text = payload.get("full_text")
    full_text = _parse_json_maybe(full_text)
    if isinstance(full_text, dict) and full_text.get("raw_text"):
        return full_text.get("raw_text")
    if isinstance(full_text, str):
        return full_text
    return None


def _build_refund_rules(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = payload.get("refund_rules")
    if not isinstance(rules, list):
        return []
    normalized = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        days = rule.get("days") or rule.get("period")
        percent = rule.get("percent") or rule.get("refund_percent")
        if days is None or percent is None:
            continue
        try:
            period = int(days)
            refund_percent = int(percent)
        except (TypeError, ValueError):
            continue
        normalized.append({
            "period": period,
            "unit": "일",
            "refund_percent": refund_percent,
        })
    normalized.sort(key=lambda item: item["period"])
    return normalized


def _infer_title(payload: Dict[str, Any]) -> str:
    name = payload.get("business_name") or payload.get("service_type")
    if isinstance(name, str) and name.strip():
        return f"{name.strip()} OCR 계약"
    return "OCR 계약"


def _duration_minutes(days: Optional[int]) -> int:
    if not days:
        return 0
    return int(days) * 24 * 60


async def _ensure_system_business(db: AsyncSession, name_hint: Optional[str]) -> int:
    system_email = "ocr-system@local"
    result = await db.execute(select(User).where(User.id == system_email))
    system_user = result.scalar_one_or_none()
    if not system_user:
        system_user = User(
            id=system_email,
            password_hash=None,
            name="OCR System",
            role="business",
        )
        db.add(system_user)
        await db.flush()

    profile_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.user_id == system_user.user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        profile = BusinessProfile(
            user_id=system_user.user_id,
            business_name=name_hint or "OCR Business",
            registration_number=None,
        )
        db.add(profile)
        await db.flush()

    return profile.id

async def request_ai_ocr(image_bytes: bytes, company_type: Optional[str]) -> dict:
    async with httpx.AsyncClient() as client:
        headers = {}
        if AI_API_KEY:
            headers["X-API-KEY"] = AI_API_KEY
        response = await client.post(
            f"{AI_SERVER_URL}/api/v1/ocr/upload",
            headers=headers,
            files={"file": ("image.png", image_bytes, "image/png")},
            data={"company_type": company_type or DEFAULT_COMPANY_TYPE},
            timeout=90.0,
        )
        response.raise_for_status()
        return response.json()


def normalize_ocr_result(result: object) -> object:
    if isinstance(result, dict) and "extracted_fields" in result:
        return result.get("extracted_fields")
    return result


async def process_ocr_request(
    image: UploadFile,
    current_user: User,
    db: AsyncSession,
    company_type: Optional[str],
) -> dict:
    if current_user.role == "business":
        result = await db.execute(select(BusinessProfile.id).where(BusinessProfile.user_id == current_user.user_id))
        profile_id = result.scalar_one_or_none()
        customer_profile_id, business_profile_id = None, profile_id
    else:
        result = await db.execute(select(CustomerProfile.id).where(CustomerProfile.user_id == current_user.user_id))
        profile_id = result.scalar_one_or_none()
        customer_profile_id, business_profile_id = profile_id, None

    if not profile_id:
        raise HTTPException(status_code=404, detail="Profile not found")

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

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

        document_id = result.lastrowid
        if not document_id:
            res = await db.execute(text("SELECT LAST_INSERT_ID()"))
            document_id = res.scalar()

        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    if not AI_SERVER_URL:
        return {"document_id": document_id, "status": "saved_only"}

    try:
        ai_result = await request_ai_ocr(image_bytes, company_type)
    except Exception as exc:
        await db.execute(text("UPDATE ocr_documents SET status='failed' WHERE id=:id"), {"id": document_id})
        await db.commit()
        return {"document_id": document_id, "status": "failed", "error": str(exc)}

    try:
        await db.execute(
            text("UPDATE ocr_documents SET status='completed', ocr_result=:result WHERE id=:id"),
            {"id": document_id, "result": json.dumps(ai_result, ensure_ascii=False)},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    return {
        "document_id": document_id,
        "status": "completed",
        "result": normalize_ocr_result(ai_result),
    }


@router.post("/request")
async def ocr_request(
    image: UploadFile = File(...),
    company_type: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await process_ocr_request(image, current_user, db, company_type)


@router.post("/upload")
async def ocr_upload(
    image: UploadFile = File(...),
    company_type: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await process_ocr_request(image, current_user, db, company_type)


@router.post("/contract")
async def create_contract_from_ocr(
    payload: OcrContractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Customer only endpoint.")

    profile_result = await db.execute(
        select(CustomerProfile).where(CustomerProfile.user_id == current_user.user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Customer profile not found.")

    doc_result = await db.execute(
        select(OCRDocument).where(OCRDocument.id == payload.document_id)
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="OCR document not found.")
    if document.customer_profile_id != profile.id:
        raise HTTPException(status_code=403, detail="Not your OCR document.")
    if document.status != "completed":
        raise HTTPException(status_code=409, detail="OCR document is not completed.")

    ocr_payload = _parse_json_maybe(document.ocr_result)
    if not isinstance(ocr_payload, dict):
        raise HTTPException(status_code=400, detail="Invalid OCR payload.")

    duration_days = payload.duration_days or ocr_payload.get("duration_days") or 30
    if isinstance(duration_days, str):
        digits = "".join(ch for ch in duration_days if ch.isdigit())
        duration_days = digits or duration_days
    try:
        duration_days = int(duration_days)
    except (TypeError, ValueError):
        duration_days = 30

    amount_krw = payload.amount_krw
    if amount_krw is None:
        amount_krw = ocr_payload.get("amount_krw") or 0
    if isinstance(amount_krw, str):
        amount_krw = amount_krw.replace(",", "")
    try:
        amount_krw = int(amount_krw)
    except (TypeError, ValueError):
        amount_krw = 0

    refund_rules = _build_refund_rules(ocr_payload)
    terms = _extract_terms(ocr_payload) or ""
    title = payload.title or _infer_title(ocr_payload)

    start_at = payload.start_at or datetime.utcnow()
    duration_minutes = _duration_minutes(duration_days)
    end_at = start_at + timedelta(minutes=duration_minutes) if duration_minutes else None

    business_id = document.business_profile_id
    if not business_id:
        business_id = await _ensure_system_business(db, ocr_payload.get("business_name"))
        document.business_profile_id = business_id

    new_pass = Pass(
        business_id=business_id,
        facility_id=None,
        title=title,
        terms=terms,
        price=Decimal(str(amount_krw)),
        duration_days=duration_days,
        duration_minutes=duration_minutes,
        contract_address=None,
        contract_chain="offchain",
        refund_rules=refund_rules,
        status="active",
    )
    db.add(new_pass)
    await db.flush()

    new_order = Order(
        user_id=current_user.user_id,
        pass_id=new_pass.id,
        amount=Decimal(str(amount_krw)),
        chain="offchain",
        status="paid",
        source_document_id=document.id,
    )
    db.add(new_order)

    new_sub = Subscription(
        user_id=current_user.user_id,
        pass_id=new_pass.id,
        start_at=start_at,
        end_at=end_at,
        status="active",
    )
    db.add(new_sub)

    await db.commit()
    return {
        "status": "success",
        "document_id": document.id,
        "pass_id": new_pass.id,
        "order_id": new_order.id,
        "subscription_id": new_sub.id,
        "start_at": start_at,
        "end_at": end_at,
        "duration_days": duration_days,
        "refund_rules": refund_rules,
    }


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
    rows = []
    for row in result:
        data = dict(row._mapping)
        if isinstance(data.get("ocr_result"), str):
            try:
                data["ocr_result"] = json.loads(data["ocr_result"])
            except Exception:
                pass
        rows.append(data)
    return rows

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

    parsed_data = row.ocr_result
    if isinstance(parsed_data, str):
        try:
            parsed_data = json.loads(parsed_data)
        except Exception:
            pass
    parsed_data = normalize_ocr_result(parsed_data)

    return {
        "id": doc_id,
        "status": row.status,
        "created_at": row.created_at,
        "parsed_data": parsed_data,
    }
