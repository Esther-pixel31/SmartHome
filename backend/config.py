import os

class Config:
    SECRET_KEY = 'devkey'
    JWT_SECRET_KEY = 'devjwt'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///data.sqlite'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
