# C:\Project\kaist\2_week\blockpass-back\app\schemas\schemas.py
from pydantic import BaseModel, EmailStr, Field
# 아래 줄이 빠져서 에러가 난 것입니다!
from typing import Literal, Optional, List

class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="로그인용 이메일 ID")
    # max_length=72 를 추가하여 Bcrypt 제한을 방어합니다.
    password: str = Field(..., min_length=4, max_length=72, description="비밀번호")
    name: str = Field(..., description="사용자 실명")
    role: Literal["customer", "business"] = Field(..., description="사용자 역할")
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class EmailCheckRequest(BaseModel):
    email: EmailStr

class ProfileUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    registration_number: Optional[str] = None
    wallet_address: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class RefundRulePayload(BaseModel):
    period: int
    unit: Literal["일", "시간", "분"]
    refund_percent: int

class PassCreateRequest(BaseModel):
    title: str
    terms: Optional[str] = None
    price: float
    duration_days: Optional[int] = None
    duration_minutes: Optional[int] = None
    contract_address: Optional[str] = None
    contract_chain: Optional[str] = None
    refund_rules: Optional[List[RefundRulePayload]] = None

class OrderPurchaseRequest(BaseModel):
    tx_hash: Optional[str] = None
    chain: Optional[str] = None
    wallet_address: Optional[str] = None
