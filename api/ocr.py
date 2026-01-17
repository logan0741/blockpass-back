import json
import os

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
import requests
from sqlalchemy import text

from db import engine

load_dotenv()

router = APIRouter(prefix="/api/ocr")

AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://172.10.5.70:8123")
AI_API_KEY = os.getenv("AI_API_KEY")
BACK_API_KEY = os.getenv("BACK_API_KEY")
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "65535"))


def require_api_key(expected_key: str | None, received_key: str | None) -> None:
    if not expected_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if received_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/request")
async def ocr_request(
    role: str = Form(...),
    profile_id: int = Form(...),
    image: UploadFile = File(...),
) -> dict:
    if role not in ("customer", "business"):
        raise HTTPException(status_code=400, detail="Invalid role")

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

    customer_profile_id = profile_id if role == "customer" else None
    business_profile_id = profile_id if role == "business" else None

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO ocr_documents (
                    customer_profile_id,
                    business_profile_id,
                    image_png,
                    status
                ) VALUES (
                    :customer_profile_id,
                    :business_profile_id,
                    :image_png,
                    'pending'
                )
                """
            ),
            {
                "customer_profile_id": customer_profile_id,
                "business_profile_id": business_profile_id,
                "image_png": image_bytes,
            },
        )
        document_id = result.lastrowid

    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI API key not configured")

    try:
        response = requests.post(
            f"{AI_SERVER_URL}/ai/ocr",
            headers={"X-API-KEY": AI_API_KEY},
            files={"image": ("image.png", image_bytes, "image/png")},
            data={
                "document_id": str(document_id),
                "role": role,
                "profile_id": str(profile_id),
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE ocr_documents SET status='failed' WHERE id=:id"),
                {"id": document_id},
            )
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc

    if response.status_code != 200:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE ocr_documents SET status='failed' WHERE id=:id"),
                {"id": document_id},
            )
        raise HTTPException(status_code=502, detail="AI returned error")

    return {"document_id": document_id, "status": "sent"}


@router.post("/callback")
async def ocr_callback(
    payload: dict,
    x_api_key: str | None = Header(default=None, alias="X-API-KEY"),
) -> dict:
    require_api_key(BACK_API_KEY, x_api_key)

    document_id = payload.get("document_id")
    result = payload.get("result")
    if not document_id or not isinstance(result, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    ocr_result = json.dumps(result)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ocr_documents
                SET ocr_result = CAST(:ocr_result AS JSON),
                    status = 'processed'
                WHERE id = :id
                """
            ),
            {"ocr_result": ocr_result, "id": document_id},
        )

    return {"status": "ok"}
