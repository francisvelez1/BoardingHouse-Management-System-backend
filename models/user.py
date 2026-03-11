from beanie import Document, Indexed
from pydantic import EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class RoleName(str, Enum):
    ADMIN       =     "ROLE_ADMIN"
    MANAGER     =     "ROLE_MANAGER"
    STAFF       =     "ROLE_STAFF"
    MAINTENANCE =     "ROLE_MAINTENANCE"
    TENANT      =     "ROLE_TENANT"


class UserStatus(str, Enum):
    ACTIVE      =      "ACTIVE"
    INACTIVE    =      "INACTIVE"
    SUSPENDED   =      "SUSPENDED"

class User(Document):
    username:          Indexed(str, unique=True)
    email:             Indexed(EmailStr, unique=True)
    password:          str        #stored in bycrip for hashing

    first_name:        Optional[str] = None
    last_name:         Optional[str] = None
    phone:             Optional[str] = None
    profile_picture:   Optional[str] = None       #filepath or Url

    role:        RoleName        =  RoleName.TENANT
    status:      UserStatus      =  UserStatus.ACTIVE

    last_login:  Optional[datetime] = None

    #audit fields

    created_at:         datetime = Field(default_factory=datetime.utcnow)
    updated_at:         datetime = Field(default_factory=datetime.utcnow)

    #beane settings
    class Settings:
        name = "user"     #Mongodb collection name

    #helper properties
    @property
    def full_name(self) -> str:
        #Returns full name or username Feedback
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    #String Representation
    def __str__(self):
        return f"User(username={self.username}, role={self.role}, status={self.status})"    
