import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://user:password@127.0.0.1:3306/blockpass",
)
engine = create_engine(DB_URL, pool_pre_ping=True)
