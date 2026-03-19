import os
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field
from pydantic_settings import BaseSettings
from models.user import User
from models.otp import OtpCode



class DataSettings(BaseSettings):
    # Pydantic will automatically look for MONGODB_URL and MONGODB_NAME in your .env
    mongodb_url: str = Field(..., alias="DATABASE_URL") 
    mongodb_name: str = Field(..., alias="MONGODB_NAME")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }
async def init_database():
    settings = DataSettings()
    client = AsyncIOMotorClient(settings.mongodb_url)
    database = client[settings.mongodb_name]

    #add models here as you create your own models

    await init_beanie(
        database=database,
        document_models = [
            User, OtpCode,
        ]
    )
    print("Connected to MongoDB:", settings.mongodb_name)
    print(f"Registered models: User")