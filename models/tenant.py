
from beanie import Document, Indexed, Link
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Annotated
from datetime import datetime, date
from enum import Enum

class TenantStatus(str, Enum):
    PENDING   = "PENDING"    # Applied but not yet approved
    ACTIVE    = "ACTIVE"     # Currently occupying a room
    INACTIVE  = "INACTIVE"   # Registered but not occupying
    MOVED_OUT = "MOVED_OUT"  # Has vacated


class IDType(str, Enum):
    PASSPORT          = "PASSPORT"
    DRIVERS_LICENSE   = "DRIVERS_LICENSE"
    NATIONAL_ID       = "NATIONAL_ID"
    SSS               = "SSS"
    PHILHEALTH        = "PHILHEALTH"
    PAGIBIG           = "PAGIBIG"
    POSTAL_ID         = "POSTAL_ID"
    VOTERS_ID         = "VOTERS_ID"
    OTHER             = "OTHER"


class EmergencyRelation(str, Enum):
    PARENT    = "PARENT"
    SPOUSE    = "SPOUSE"
    SIBLING   = "SIBLING"
    RELATIVE  = "RELATIVE"
    FRIEND    = "FRIEND"
    GUARDIAN  = "GUARDIAN"
    OTHER     = "OTHER"


class CivilStatus(str, Enum):
    SINGLE   = "SINGLE"
    MARRIED  = "MARRIED"
    WIDOWED  = "WIDOWED"
    DIVORCED = "DIVORCED"
    OTHER    = "OTHER"


class Gender(str, Enum):
    MALE              = "MALE"
    FEMALE            = "FEMALE"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


# ================================================================
# EMBEDDED SUB-DOCUMENTS  (BaseModel — NOT separate collections)
# ================================================================

class EmergencyContact(BaseModel):
    """
    Embedded contact person for emergencies.
    Stored directly inside the Tenant document.
    """
    full_name:    str
    phone:        str
    relationship: EmergencyRelation = EmergencyRelation.OTHER
    email:        Optional[EmailStr] = None
    address:      Optional[str]      = None


class GovernmentID(BaseModel):
    """
    Embedded ID verification info.
    Stores a single government-issued ID per tenant.
    Extend to List[GovernmentID] if multiple IDs are needed.
    """
    id_type:     IDType
    id_number:   str
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    verified:    bool           = False         # Set True after staff review
    verified_by: Optional[str]  = None          # Username of verifying staff
    verified_at: Optional[datetime] = None


class Address(BaseModel):
    """
    Embedded permanent/home address of the tenant.
    Useful for billing, contracts, and emergency contact.
    """
    street:   Optional[str] = None
    barangay: Optional[str] = None
    city:     Optional[str] = None
    province: Optional[str] = None
    zip_code: Optional[str] = None
    country:  str           = "Philippines"


# ================================================================
# MAIN DOCUMENT
# ================================================================

class Tenant(Document):
    """
    Represents a boarding house tenant.

    Relationships:
    - Links to User      (one Tenant profile per User account)
    - Links to Room      (current assigned room, None if unassigned)

    Embedded:
    - GovernmentID       (ID verification)
    - EmergencyContact   (next-of-kin / emergency person)
    - Address            (permanent home address)

    Financial tracking:
    - outstanding_balance updated by BillingService / PaymentService
    - deposit tracked separately from monthly rent
    """

    # ── Link to User Account ─────────────────────────────────────
    # The User document holds login credentials (username, email,
    # password, role). Tenant holds the profile / tenancy data.
    # Use fetch_links=True when you need User fields alongside Tenant.
    user_id: Optional[str] = None                                            # type: ignore[name-defined]

    # ── Personal Information ──────────────────────────────────────
    first_name:    str
    last_name:     str
    middle_name:   Optional[str]      = None
    date_of_birth: Optional[date]     = None
    gender:        Optional[Gender]   = None
    civil_status:  Optional[CivilStatus] = None
    nationality:   str                = "Filipino"

    # Contact — indexed for fast lookups by phone / email
    phone:         Annotated[str, Indexed(unique=True)]
    email:         Annotated[EmailStr, Indexed(unique=True)]

    # Profile picture — stores filepath or cloud URL (e.g. Cloudinary)
    profile_picture: Optional[str] = None

    # Permanent home address (not the room address)
    home_address: Optional[Address] = None

    # ── Occupation / Background ───────────────────────────────────
    occupation:  Optional[str] = None    # e.g. "Student", "Employee"
    employer:    Optional[str] = None    # Company / school name
    monthly_income: Optional[float] = None

    # ── ID Verification ───────────────────────────────────────────
    government_id: Optional[GovernmentID] = None

    # ── Emergency Contact ─────────────────────────────────────────
    emergency_contact: Optional[EmergencyContact] = None

    # ── Room / Occupancy ─────────────────────────────────────────
    # None = not yet assigned to a room
    # Set by LeaseService when a lease is created / terminated
    room_id: Optional[str] = None                     # type: ignore[name-defined]
    move_in_date:  Optional[datetime]     = None
    move_out_date: Optional[datetime]     = None

    # ── Status ────────────────────────────────────────────────────
    status: TenantStatus = TenantStatus.PENDING

    # ── Financial Summary ─────────────────────────────────────────
    # These are running totals updated by BillingService /
    # PaymentService — do NOT set these manually.
    outstanding_balance: float = 0.0      # Current unpaid amount (PHP)
    total_paid:          float = 0.0      # Lifetime total payments made

    # Security deposit tracking
    deposit_paid:        bool          = False
    deposit_amount:      Optional[float] = None   # Amount actually paid
    deposit_date:        Optional[datetime] = None

    # ── Notes ─────────────────────────────────────────────────────
    # Internal staff/admin notes — not visible to the tenant
    notes: Optional[str] = None

    # ── Audit Fields ──────────────────────────────────────────────
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Tracks which staff/admin registered or last updated this tenant
    created_by: Optional[str] = None   # Username of registering staff
    updated_by: Optional[str] = None   # Username of last editor

    # ── Beanie Settings ───────────────────────────────────────────
    class Settings:
        name = "tenants"   # MongoDB collection name

    # ── Computed Properties ───────────────────────────────────────

    @property
    def full_name(self) -> str:
        """Returns 'First Middle Last' or 'First Last' if no middle name."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)

    @property
    def is_active(self) -> bool:
        """True if tenant is currently active."""
        return self.status == TenantStatus.ACTIVE

    @property
    def is_occupying(self) -> bool:
        """True if tenant is currently assigned to a room."""
        return self.room_id is not None

    @property
    def has_outstanding_balance(self) -> bool:
        """True if tenant owes any amount."""
        return self.outstanding_balance > 0

    @property
    def is_id_verified(self) -> bool:
        """True if the submitted government ID has been verified by staff."""
        return self.government_id is not None and self.government_id.verified

    @property
    def age(self) -> Optional[int]:
        """Returns tenant age calculated from date_of_birth, or None."""
        if not self.date_of_birth:
            return None
        today = date.today()
        return (
            today.year - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    # ── String Representation ─────────────────────────────────────

    def __str__(self) -> str:
        return (
            f"Tenant("
            f"name={self.full_name}, "
            f"status={self.status.value}, "
            f"room={self.room_id}, "
            f"balance={self.outstanding_balance:.2f}"
            f")"
        )

    def __repr__(self) -> str:
        return (
            f"<Tenant id={self.id} "
            f"name='{self.full_name}' "
            f"status='{self.status.value}'>"
        )