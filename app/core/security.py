# C:\Project\kaist\2_week\blockpass-back\app\core\security.py
import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi import HTTPException
load_dotenv()

# 보안 설정
SECRET_KEY = os.getenv("SECRET_KEY", "BLOCKPASS_TEMP_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 비밀번호 해싱 (암호화)
def get_password_hash(password: str) -> str:
    try:
        # 72바이트 제한을 한 번 더 체크합니다.
        if len(password.encode('utf-8')) > 72:
            raise ValueError("Password is too long")
        return pwd_context.hash(password)
    except ValueError:
        # 서버가 터지는 대신 사용자에게 에러 메시지를 보냅니다.
        raise HTTPException(status_code=400, detail="비밀번호가 너무 깁니다. (최대 72자)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"암호화 오류: {str(e)}")

# 비밀번호 검증
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# JWT 액세스 토큰 생성
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)