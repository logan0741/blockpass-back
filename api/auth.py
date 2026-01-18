# C:\Project\kaist\2_week\blockpass-back\api\auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordRequestForm
from app.core.db import get_db
from app.models.models import User, BusinessProfile, CustomerProfile
from app.schemas.schemas import UserCreate, UserLogin, Token
from app.core.security import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    SECRET_KEY, 
    ALGORITHM
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# [허점 1 해결] Swagger UI 자물쇠 버튼을 위한 설정. 전체 경로를 정확히 입력합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# [보안 로직] 토큰을 검증하여 현재 로그인한 사용자를 식별하는 의존성
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않거나 만료되었습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 토큰 해독
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub") # 토큰 생성 시 넣었던 이메일 ID
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # DB에서 실시간 유저 존재 여부 확인
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

# 1. 회원가입 (비밀번호 암호화 + 프로필 자동 생성)
@router.post("/register")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # 중복 체크
    check_query = await db.execute(select(User).where(User.id == user_data.email))
    if check_query.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="이미 등록된 이메일입니다."
        )
    
    # User 생성
    new_user = User(
        id=user_data.email, 
        password_hash=get_password_hash(user_data.password),
        name=user_data.name,
        role=user_data.role
    )
    db.add(new_user)
    
    try:
        await db.flush() # user_id 확보
        
        # 역할별 프로필 생성
        if user_data.role == "business":
            profile = BusinessProfile(
                user_id=new_user.user_id, 
                business_name=f"{user_data.name}의 시설"
            )
        else:
            profile = CustomerProfile(user_id=new_user.user_id)
        
        db.add(profile)
        await db.commit() # 최종 저장
        return {
            "status": "success", 
            "message": f"{user_data.name}님, 가입을 환영합니다!",
            "user_id": new_user.user_id
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"가입 처리 중 오류 발생: {str(e)}"
        )

# 2. 로그인 (JWT 토큰 발행)
@router.post("/login", response_model=Token)
async def login(
    # [허점 2 해결] 표준 폼 데이터를 사용합니다.
    # Swagger 자물쇠 버튼과 프런트엔드 통신을 모두 지원합니다.
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    # form_data.username 이 우리가 입력한 이메일(ID)이 됩니다.
    result = await db.execute(select(User).where(User.id == form_data.username))
    user = result.scalar_one_or_none()
    
    # 비밀번호 검증
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 토큰 발행
    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role,
        # [추가] 프런트엔드 App.jsx의 화면 전환을 돕는 메타데이터
        "user_info": {
            "name": user.name,
            "next_screen": "role" if not user.role else (
                "business_main" if user.role == "business" else "customer_main"
            )
        }
    }
# 3. 내 정보 조회 (토큰 인증 필요)
@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    # get_current_user 덕분에 '이미 로그인된 상태'임이 보장됩니다.
    return {
        "email": current_user.id,
        "name": current_user.name,
        "role": current_user.role,
        "created_at": current_user.created_at
    }
# 4. 프로필 정보 업데이트 (← 여기부터 새로 추가!)
@router.patch("/profile")
async def update_profile(
    business_name: str = None,
    registration_number: str = None,
    wallet_address: str = None,
    address: str = None,  # 추가
    lat: float = None,  # 추가
    lng: float = None,  # 추가
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # 사업자 프로필 업데이트
        if current_user.role == "business":
            result = await db.execute(
                select(BusinessProfile).where(BusinessProfile.user_id == current_user.user_id)
            )
            profile = result.scalar_one_or_none()
            
            if not profile:
                raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다.")
            
            if business_name:
                profile.business_name = business_name
            if registration_number:
                profile.registration_number = registration_number
        
        # 지갑 주소는 User 테이블에 저장
        if wallet_address:
            current_user.wallet_address = wallet_address
        
        await db.commit()
        
        return {
            "status": "success",
            "message": "프로필이 업데이트되었습니다."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")