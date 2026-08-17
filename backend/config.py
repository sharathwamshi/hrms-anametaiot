import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)
    JWT_TOKEN_LOCATION = ["headers"]

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "anametaiot_hrms")

    # root user with empty password -> "root:@host" (no colon-password segment)
    _password_segment = f":{DB_PASSWORD}" if DB_PASSWORD else ""
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}{_password_segment}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB uploads
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")

    COMPANY_NAME = os.environ.get("COMPANY_NAME", "AnametaIOT HRMS")
    POWERED_BY = os.environ.get("POWERED_BY", "+veGroww")

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
