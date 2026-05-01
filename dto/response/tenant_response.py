from pydantic import BaseModel, EmailStr
from beanie import PydanticObjectId
from typing import Optional
from datetime import datetime, date

from models.tenant import (
    Gender,
    CivilStatus,
    IDType,
    EmergencyRelation,
    TenantStatus,   # make sure this exists in your model
)


# ================================================================
# EMBEDDED RESPONSE SCHEMAS
# ================================================================

class GovernmentIDResponse(BaseModel):
    id_type:     IDType
    id_number:   str
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    verified:    bool = False       # staff verifies manually


class EmergencyContactResponse(BaseModel):
    full_name:    str
    phone:        str
    relationship: EmergencyRelation
    email:        Optional[EmailStr] = None
    address:      Optional[str]      = None


class AddressResponse(BaseModel):
    street:   Optional[str] = None
    barangay: Optional[str] = None
    city:     Optional[str] = None
    province: Optional[str] = None
    zip_code: Optional[str] = None
    country:  str = "Philippines"


# ================================================================
# MAIN TENANT RESPONSE
# ================================================================

class TenantResponse(BaseModel):
    """
    Returned by:
      GET  /api/tenants/{tenant_id}
      POST /api/tenants
      PATCH /api/tenants/{tenant_id}

    Never expose sensitive fields here — no passwords, no raw IDs
    unless needed by frontend.
    """

    # ── Identity ──────────────────────────────────────────────
    id:      str                    # MongoDB _id as string
    user_id: str                    # linked User account

    # ── Personal Info ─────────────────────────────────────────
    first_name:    str
    last_name:     str
    middle_name:   Optional[str]         = None
    full_name:     str                   # computed: "Juan S. dela Cruz"
    date_of_birth: Optional[date]        = None
    gender:        Optional[Gender]      = None
    civil_status:  Optional[CivilStatus] = None
    nationality:   str = "Filipino"

    # ── Contact ───────────────────────────────────────────────
    phone: str
    email: EmailStr

    # ── Occupation ────────────────────────────────────────────
    occupation:     Optional[str]   = None
    employer:       Optional[str]   = None
    monthly_income: Optional[float] = None

    # ── Room assignment ───────────────────────────────────────
    room_id:      Optional[str]      = None   # null if not yet assigned
    move_in_date: Optional[datetime] = None
    status:       TenantStatus

    # ── Deposit ───────────────────────────────────────────────
    deposit_amount: Optional[float]   = None
    deposit_date:   Optional[datetime] = None
    deposit_paid:   bool = False

    # ── Sub-documents ─────────────────────────────────────────
    home_address:      Optional[AddressResponse]          = None
    emergency_contact: Optional[EmergencyContactResponse] = None
    government_id:     Optional[GovernmentIDResponse]     = None

    # ── Notes ─────────────────────────────────────────────────
    notes: Optional[str] = None

    # ── Audit ─────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "665f1c2e8a4b2c001f3d9a11",
                "user_id": "665f1c2e8a4b2c001f3d9a00",
                "first_name": "Juan",
                "last_name": "dela Cruz",
                "middle_name": "Santos",
                "full_name": "Juan S. dela Cruz",
                "date_of_birth": "1995-06-15",
                "gender": "MALE",
                "civil_status": "SINGLE",
                "nationality": "Filipino",
                "phone": "09171234567",
                "email": "juan@email.com",
                "occupation": "Student",
                "employer": "University of the Philippines",
                "monthly_income": 5000.00,
                "room_id": "665f1c2e8a4b2c001f3d9b22",
                "move_in_date": "2024-06-01T08:00:00",
                "status": "ACTIVE",
                "deposit_amount": 5000.00,
                "deposit_date": "2024-06-01T09:30:00",
                "deposit_paid": True,
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
                    "expiry_date": "2032-01-10",
                    "verified": False
                },
                "notes": "Prefers quiet hours after 10pm.",
                "created_at": "2024-06-01T08:00:00",
                "updated_at": "2024-06-01T08:00:00"
            }
        }
    }


# ================================================================
# TENANT LIST RESPONSE
# ================================================================

class TenantSummaryResponse(BaseModel):
    """
    Lighter version for list views — GET /api/tenants
    Only includes fields needed for the table row.
    No sub-documents to keep the payload small.
    """
    id:           str
    full_name:    str
    phone:        str
    email:        EmailStr
    room_id:      Optional[str]  = None
    status:       TenantStatus
    deposit_paid: bool
    move_in_date: Optional[datetime] = None
    created_at:   datetime


class TenantListResponse(BaseModel):
    """
    Paginated list wrapper for GET /api/tenants
    """
    total:   int
    page:    int
    limit:   int
    tenants: list[TenantSummaryResponse]


# ================================================================
# HELPER — convert Tenant model → TenantResponse
# ================================================================

def to_tenant_response(tenant) -> TenantResponse:
    """
    Maps a Beanie Tenant document to TenantResponse.
    Call this in your service or controller after fetching from DB.

    Usage:
        tenant = await find_by_id(tenant_id)
        return to_tenant_response(tenant)
    """
    middle = f" {tenant.middle_name[0]}." if tenant.middle_name else ""
    full_name = f"{tenant.first_name}{middle} {tenant.last_name}"

    return TenantResponse(
        id            = str(tenant.id),
        user_id       = str(tenant.user_id),
        first_name    = tenant.first_name,
        last_name     = tenant.last_name,
        middle_name   = tenant.middle_name,
        full_name     = full_name,
        date_of_birth = tenant.date_of_birth,
        gender        = tenant.gender,
        civil_status  = tenant.civil_status,
        nationality   = tenant.nationality,
        phone         = tenant.phone,
        email         = tenant.email,
        occupation    = tenant.occupation,
        employer      = tenant.employer,
        monthly_income= tenant.monthly_income,
        room_id       = str(tenant.room_id) if tenant.room_id else None,
        move_in_date  = tenant.move_in_date,
        status        = tenant.status,
        deposit_amount= tenant.deposit_amount,
        deposit_date  = tenant.deposit_date,
        deposit_paid  = tenant.deposit_paid,
        home_address  = tenant.home_address,
        emergency_contact = tenant.emergency_contact,
        government_id = tenant.government_id,
        notes         = tenant.notes,
        created_at    = tenant.created_at,
        updated_at    = tenant.updated_at,
    )


def to_tenant_summary(tenant) -> TenantSummaryResponse:
    """
    Maps a Beanie Tenant document to TenantSummaryResponse.
    Use this for list endpoints to keep payloads light.
    """
    middle = f" {tenant.middle_name[0]}." if tenant.middle_name else ""
    full_name = f"{tenant.first_name}{middle} {tenant.last_name}"

    return TenantSummaryResponse(
        id           = str(tenant.id),
        full_name    = full_name,
        phone        = tenant.phone,
        email        = tenant.email,
        room_id      = str(tenant.room_id) if tenant.room_id else None,
        status       = tenant.status,
        deposit_paid = tenant.deposit_paid,
        move_in_date = tenant.move_in_date,
        created_at   = tenant.created_at,
    )