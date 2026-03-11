import os
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from models import user

load_dotenv()


class DataSettings(BaseSettings):
    mongodb_url: str = os.getenv("DATABASE_URL")
    mongodb_name: str = os.getenv("MONGODB_NAME")

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
            user,
        ]
    )
    print("Connected to MongoDB:", settings.mongodb_name)
    print(f"Registered models: User")