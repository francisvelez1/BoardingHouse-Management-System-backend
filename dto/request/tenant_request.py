from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from beanie import PydanticObjectId
from typing import Optional
from datetime import datetime, date

from models.tenant import (
    Gender,
    CivilStatus,
    IDType,
    EmergencyRelation,
)


# ================================================================
# EMBEDDED REQUEST SCHEMAS
# ================================================================

class GovernmentIDRequest(BaseModel):
    """
    Submitted government ID details.
    Verification is always False on submission — staff verifies manually.
    """
    id_type:     IDType
    id_number:   str    = Field(..., min_length=3, max_length=50)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None

    @field_validator("id_number")
    @classmethod
    def strip_id_number(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def expiry_must_be_after_issued(self) -> "GovernmentIDRequest":
        if self.issued_date and self.expiry_date:
            if self.expiry_date <= self.issued_date:
                raise ValueError("expiry_date must be after issued_date.")
        return self


class EmergencyContactRequest(BaseModel):
    """
    Emergency contact person for the tenant.
    """
    full_name:    str              = Field(..., min_length=2, max_length=100)
    phone:        str              = Field(..., min_length=7, max_length=20)
    relationship: EmergencyRelation = EmergencyRelation.OTHER
    email:        Optional[EmailStr] = None
    address:      Optional[str]    = Field(default=None, max_length=255)

    @field_validator("full_name", "phone")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


class AddressRequest(BaseModel):
    """
    Permanent home address of the tenant.
    """
    street:   Optional[str] = Field(default=None, max_length=255)
    barangay: Optional[str] = Field(default=None, max_length=100)
    city:     Optional[str] = Field(default=None, max_length=100)
    province: Optional[str] = Field(default=None, max_length=100)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    country:  str           = Field(default="Philippines", max_length=100)

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.strip().isdigit():
            raise ValueError("zip_code must contain digits only.")
        return v.strip() if v else None


# ================================================================
# TENANT CREATE REQUEST
# ================================================================

class TenantCreateRequest(BaseModel):
    """
    Payload for POST /api/tenants

    Required:
    - user_id       → must reference an existing User account
    - first_name, last_name
    - phone, email  → must be unique across all tenants
    
    Optional:
    - All personal, occupation, address, emergency contact, and ID fields
    """

    # ── Link to User ─────────────────────────────────────────
    user_id: PydanticObjectId = Field(
        ...,
        description="MongoDB ObjectId of the linked User account."
    )

    # ── Personal Info ─────────────────────────────────────────
    first_name:    str              = Field(..., min_length=1, max_length=50)
    last_name:     str              = Field(..., min_length=1, max_length=50)
    middle_name:   Optional[str]    = Field(default=None, max_length=50)
    date_of_birth: Optional[date]   = None
    gender:        Optional[Gender] = None
    civil_status:  Optional[CivilStatus] = None
    nationality:   str              = Field(default="Filipino", max_length=60)

    # ── Contact ───────────────────────────────────────────────
    phone: str     = Field(..., min_length=7,  max_length=20)
    email: EmailStr

    # ── Occupation ────────────────────────────────────────────
    occupation:     Optional[str]   = Field(default=None, max_length=100)
    employer:       Optional[str]   = Field(default=None, max_length=100)
    monthly_income: Optional[float] = Field(default=None, ge=0)

    # ── Embedded Sub-documents ────────────────────────────────
    home_address:      Optional[AddressRequest]          = None
    emergency_contact: Optional[EmergencyContactRequest] = None
    government_id:     Optional[GovernmentIDRequest]     = None

    # ── Validators ────────────────────────────────────────────

    @field_validator("first_name", "last_name", "phone", "nationality")
    @classmethod
    def strip_and_title(cls, v: str) -> str:
        return v.strip()

    @field_validator("middle_name", "occupation", "employer")
    @classmethod
    def strip_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = v.strip().replace("+", "").replace("-", "").replace(" ", "")
        if not digits.isdigit():
            raise ValueError("Phone number must contain digits only (spaces, +, - allowed).")
        return v.strip()

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v: Optional[date]) -> Optional[date]:
        if v:
            today = date.today()
            age = (
                today.year - v.year
                - ((today.month, today.day) < (v.month, v.day))
            )
            if age < 18:
                raise ValueError("Tenant must be at least 18 years old.")
            if age > 120:
                raise ValueError("Invalid date of birth.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "665f1c2e8a4b2c001f3d9a11",
                "first_name": "Juan",
                "last_name": "dela Cruz",
                "middle_name": "Santos",
                "date_of_birth": "1995-06-15",
                "gender": "MALE",
                "civil_status": "SINGLE",
                "nationality": "Filipino",
                "phone": "09171234567",
                "email": "juan@email.com",
                "occupation": "Student",
                "employer": "University of the Philippines",
                "monthly_income": 5000.00,
                "home_address": {
                    "street": "123 Rizal St.",
                    "barangay": "Poblacion",
                    "city": "Bacolod",
                    "province": "Negros Occidental",
                    "zip_code": "6100",
                    "country": "Philippines"
                },
                "emergency_contact": {
                    "full_name": "Maria dela Cruz",
                    "phone": "09181234567",
                    "relationship": "PARENT",
                    "email": "maria@email.com",
                    "address": "123 Rizal St. Bacolod City"
                },
                "government_id": {
                    "id_type": "NATIONAL_ID",
                    "id_number": "1234-5678-9012",
                    "issued_date": "2022-01-10",
                    "expiry_date": "2032-01-10"
                }
            }
        }
    }


# ================================================================
# TENANT UPDATE REQUEST
# ================================================================

class TenantUpdateRequest(BaseModel):
    """
    Payload for PATCH /api/tenants/{tenant_id}

    All fields are optional — only fields included in the
    request body will be updated (true PATCH behavior).
    Omitting a field means 'leave it unchanged', not 'set to null'.
    """

    # ── Personal Info ─────────────────────────────────────────
    first_name:    Optional[str]         = Field(default=None, min_length=1, max_length=50)
    last_name:     Optional[str]         = Field(default=None, min_length=1, max_length=50)
    middle_name:   Optional[str]         = Field(default=None, max_length=50)
    date_of_birth: Optional[date]        = None
    gender:        Optional[Gender]      = None
    civil_status:  Optional[CivilStatus] = None
    nationality:   Optional[str]         = Field(default=None, max_length=60)

    # ── Contact ───────────────────────────────────────────────
    phone: Optional[str]      = Field(default=None, min_length=7, max_length=20)
    email: Optional[EmailStr] = None

    # ── Occupation ────────────────────────────────────────────
    occupation:     Optional[str]   = Field(default=None, max_length=100)
    employer:       Optional[str]   = Field(default=None, max_length=100)
    monthly_income: Optional[float] = Field(default=None, ge=0)

    # ── Notes ─────────────────────────────────────────────────
    notes: Optional[str] = Field(default=None, max_length=1000)

    # ── Embedded Sub-documents ────────────────────────────────
    home_address:      Optional[AddressRequest]          = None
    emergency_contact: Optional[EmergencyContactRequest] = None
    government_id:     Optional[GovernmentIDRequest]     = None

    # ── Validators ────────────────────────────────────────────

    @field_validator("first_name", "last_name", "nationality")
    @classmethod
    def strip_strings(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            digits = v.strip().replace("+", "").replace("-", "").replace(" ", "")
            if not digits.isdigit():
                raise ValueError("Phone number must contain digits only (spaces, +, - allowed).")
        return v.strip() if v else None

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v: Optional[date]) -> Optional[date]:
        if v:
            today = date.today()
            age = (
                today.year - v.year
                - ((today.month, today.day) < (v.month, v.day))
            )
            if age < 18:
                raise ValueError("Tenant must be at least 18 years old.")
            if age > 120:
                raise ValueError("Invalid date of birth.")
        return v

    @model_validator(mode="after")
    def at_least_one_field_required(self) -> "TenantUpdateRequest":
        provided = {
            k: v for k, v in self.model_dump().items() if v is not None
        }
        if not provided:
            raise ValueError("At least one field must be provided for update.")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "Juan",
                "phone": "09171234567",
                "occupation": "Software Engineer",
                "notes": "Prefers quiet hours after 10pm."
            }
        }
    }


# ================================================================
# ASSIGN ROOM REQUEST
# ================================================================

class AssignRoomRequest(BaseModel):
    """
    Payload for PATCH /api/tenants/{tenant_id}/assign-room
    """
    room_id:      PydanticObjectId = Field(
        ...,
        description="MongoDB ObjectId of the room to assign."
    )
    move_in_date: datetime = Field(
        default_factory=datetime.utcnow,
        description="Move-in date and time. Defaults to now if not provided."
    )

    @field_validator("move_in_date")
    @classmethod
    def move_in_not_in_future(cls, v: datetime) -> datetime:
        if v > datetime.utcnow():
            raise ValueError("move_in_date cannot be in the future.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "room_id": "665f1c2e8a4b2c001f3d9b22",
                "move_in_date": "2024-06-01T08:00:00"
            }
        }
    }


# ================================================================
# DEPOSIT PAYMENT REQUEST
# ================================================================

class DepositPaymentRequest(BaseModel):
    """
    Payload for PATCH /api/tenants/{tenant_id}/deposit
    """
    amount:       float    = Field(..., gt=0, description="Deposit amount in PHP. Must be greater than 0.")
    deposit_date: datetime = Field(
        default_factory=datetime.utcnow,
        description="Date the deposit was received. Defaults to now."
    )

    @field_validator("deposit_date")
    @classmethod
    def deposit_not_in_future(cls, v: datetime) -> datetime:
        if v > datetime.utcnow():
            raise ValueError("deposit_date cannot be in the future.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "amount": 5000.00,
                "deposit_date": "2024-06-01T09:30:00"
            }
        }
    }