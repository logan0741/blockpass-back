# C:\Project\kaist\2_week\blockpass-back\main.py
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles # [신규] 이미지 조회를 위한 정적 파일 설정

# 모든 라우터 모듈 임포트 완료
from api.health import router as health_router
from api.auth import router as auth_router 
from api.ocr import router as ocr_router
from api.facilities import router as facility_router # 추가
from api.orders import router as order_router
from api.business import router as business_router
# from api.contracts import router as contract_router # 계약서 기능 활성화 시 주석 해제

app = FastAPI(
    title="BlockPass Modular Backend",
    description="인증, OCR, 정적 파일 서빙이 통합된 최종 백엔드 시스템",
    version="0.3.0",
    # Swagger UI에서 자물쇠 버튼을 활성화하기 위한 설정
    swagger_ui_parameters={"operationsSorter": "method"} 
)

# 1. CORS 설정 최적화 (안드로이드 및 웹 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 개발 중에는 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 업로드 사진 조회를 위한 정적 경로 설정 (허점 1 해결)
# 서버 로컬의 static/uploads 폴더를 /static 주소로 연결합니다.
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. 글로벌 에러 핸들러 (서버 안정성 확보)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "서버 내부 에러가 발생했습니다.", "detail": str(exc)},
    )

# 4. 라우터 통합 등록 (버전 관리 포함)
app.include_router(health_router, prefix="/api/v1", tags=["System"])
app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(ocr_router, prefix="/api/v1", tags=["OCR"])
app.include_router(facility_router, prefix="/api/v1") # 라우터 등록
app.include_router(order_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
# app.include_router(contract_router, prefix="/api/v1", tags=["Contract"])

@app.get("/")
async def root():
    return {
        "project": "BlockPass",
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/db/health"
    }

if __name__ == "__main__":
    import uvicorn
    # reload=True 설정으로 코드 수정 시 자동 반영
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
