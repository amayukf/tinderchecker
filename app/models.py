from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    referred_by = Column(BigInteger, nullable=True)
    referral_verified = Column(Boolean, default=False)  # True = referral confirmed (anti-fraud)
    referral_count = Column(Integer, default=0)  # Only verified referrals
    query_count = Column(Integer, default=0)  # Track user activity for anti-fraud
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    username_or_url = Column(String, index=True)
    status = Column(String)  # success, error, not_found
    created_at = Column(DateTime(timezone=True), server_default=func.now())
