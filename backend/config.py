import os
from datetime import timedelta

class Config:
    SECRET_KEY = "devkey"
    JWT_SECRET_KEY = "devjwt"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError("DATABASE_URL is required")
