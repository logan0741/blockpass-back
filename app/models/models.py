# C:\Project\kaist\2_week\blockpass-back\app\models\models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, DECIMAL, Date, LargeBinary, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base

# 1. 사용자 및 프로필 그룹
class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(50), nullable=False, unique=True) # 프론트엔드 로그인 ID
    password_hash = Column(String(255))
    name = Column(String(50))
    role = Column(String(20)) # 'customer' | 'business'
    wallet_address = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계 설정
    business_profile = relationship("BusinessProfile", back_populates="user", uselist=False)
    customer_profile = relationship("CustomerProfile", back_populates="user", uselist=False)
    orders = relationship("Order", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")

class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    business_name = Column(String(100))
    registration_number = Column(String(50))

    user = relationship("User", back_populates="business_profile")
    facilities = relationship("Facility", back_populates="business")
    passes = relationship("Pass", back_populates="business")
    ocr_docs = relationship("OCRDocument", back_populates="business_profile")

class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="customer_profile")
    ocr_docs = relationship("OCRDocument", back_populates="customer_profile")

# 2. 시설 및 이용권 그룹
class Facility(Base):
    __tablename__ = "facilities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    name = Column(String(100))
    category = Column(String(50)) # gym | studyroom | etc
    address = Column(String(255))
    lat = Column(DECIMAL(10, 8))
    lng = Column(DECIMAL(11, 8))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    business = relationship("BusinessProfile", back_populates="facilities")
    passes = relationship("Pass", back_populates="facility")

class Pass(Base):
    __tablename__ = "passes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    title = Column(String(100))
    terms = Column(Text)
    price = Column(DECIMAL(20, 8)) # ETH
    duration_days = Column(Integer)
    duration_minutes = Column(Integer)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    business = relationship("BusinessProfile", back_populates="passes")
    facility = relationship("Facility", back_populates="passes")
    refund_policies = relationship("RefundPolicy", back_populates="target_pass")

class RefundPolicy(Base):
    __tablename__ = "refund_policies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pass_id = Column(Integer, ForeignKey("passes.id"), nullable=False)
    name = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    target_pass = relationship("Pass", back_populates="refund_policies")
    rules = relationship("RefundPolicyRule", back_populates="policy")

class RefundPolicyRule(Base):
    __tablename__ = "refund_policy_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    refund_policy_id = Column(Integer, ForeignKey("refund_policies.id"), nullable=False)
    usage_percent = Column(Integer)
    refund_percent = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    policy = relationship("RefundPolicy", back_populates="rules")

# 3. 주문, 구독, 블록체인 연동 그룹
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    pass_id = Column(Integer, ForeignKey("passes.id"), nullable=False)
    amount = Column(DECIMAL(20, 8))
    status = Column(String(20), default="paid") # paid | refunded | cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="orders")
    pass_info = relationship("Pass")
    blockchain_contract = relationship("BlockchainContract", back_populates="order", uselist=False)
    refunds = relationship("Refund", back_populates="order")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    pass_id = Column(Integer, ForeignKey("passes.id"), nullable=False)
    start_at = Column(DateTime(timezone=True))
    end_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="active") # active | expired | refunded
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="subscriptions")

class BlockchainContract(Base):
    __tablename__ = "blockchain_contracts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    contract_address = Column(String(100))
    chain = Column(String(50))
    status = Column(String(20)) # deployed | settled | refunded
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="blockchain_contract")

class Refund(Base):
    __tablename__ = "refunds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    refund_amount = Column(Integer)
    reason = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="refunds")

# 4. OCR 전용 테이블
class OCRDocument(Base):
    __tablename__ = "ocr_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_profile_id = Column(Integer, ForeignKey("customer_profiles.id"), nullable=True)
    business_profile_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=True)
    image_png = Column(LargeBinary(length=(2**32)-1)) # LONGBLOB 대응
    ocr_result = Column(JSON) # 분석 결과 JSON 저장
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile", back_populates="ocr_docs")
    business_profile = relationship("BusinessProfile", back_populates="ocr_docs")
