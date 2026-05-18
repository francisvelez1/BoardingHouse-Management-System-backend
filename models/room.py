from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ================================================================
# ENUMS
# ================================================================

class RoomStatus(str, Enum):
    VACANT      = "VACANT"       # Available for new tenant
    OCCUPIED    = "OCCUPIED"     # Currently occupied
    MAINTENANCE = "MAINTENANCE"  # Under repair, not available
    RESERVED    = "RESERVED"     # Reserved but not yet occupied


class RoomType(str, Enum):
    SINGLE      = "SINGLE"       # 1 occupant
    DOUBLE      = "DOUBLE"       # 2 occupants
    STUDIO      = "STUDIO"       # Studio type
    DORMITORY   = "DORMITORY"    # Multiple occupants
    SUITE       = "SUITE"        # Premium room


class FloorLevel(str, Enum):
    GROUND  = "GROUND"
    SECOND  = "SECOND"
    THIRD   = "THIRD"
    FOURTH  = "FOURTH"
    FIFTH   = "FIFTH"


# ================================================================
# EMBEDDED SUB-DOCUMENTS
# ================================================================

class RoomAmenity(BaseModel):
    """
    Embedded amenities included in the room.
    e.g. aircon, wifi, private bathroom, ref, etc.
    """
    name:        str
    description: Optional[str] = None
    is_working:  bool          = True   # False if amenity is broken


class RoomDimension(BaseModel):
    """
    Physical dimensions of the room.
    """
    length_sqm: Optional[float] = None   # length in square meters
    width_sqm:  Optional[float] = None   # width in square meters

    @property
    def area_sqm(self) -> Optional[float]:
        if self.length_sqm and self.width_sqm:
            return round(self.length_sqm * self.width_sqm, 2)
        return None


# ================================================================
# MAIN DOCUMENT
# ================================================================

class Room(Document):
    """
    Represents a physical room in the boarding house.

    Relationships:
    - Linked from Tenant.room_id  (one Room → one active Tenant)
    - Linked from Lease.room_id   (one Room → many historical Leases)

    Embedded:
    - RoomAmenity   (list of included amenities)
    - RoomDimension (physical size)

    Financial:
    - monthly_rate  is the base rent used by BillingService
    - deposit_multiplier determines the required security deposit
      e.g. deposit = monthly_rate * deposit_multiplier
    """

    # ── Room Identity ─────────────────────────────────────────
    room_number:  str              # e.g. "101", "2A", "GF-03"
    floor_level:  Optional[FloorLevel] = None
    room_type:    RoomType         = RoomType.SINGLE
    description:  Optional[str]   = None   # short description for listings

    # ── Property Info ─────────────────────────────────────────
    property_name: Optional[str] = None
    location:      Optional[str] = None   # City / Area
    address:       Optional[str] = None   # Full street address

    # ── Capacity ──────────────────────────────────────────────
    max_occupants:     int   = Field(default=1, ge=1)
    current_occupants: int   = Field(default=0, ge=0)

    # ── Status ────────────────────────────────────────────────
    status: RoomStatus = RoomStatus.VACANT

    # ── Financial ─────────────────────────────────────────────
    # monthly_rate is the base rent in PHP
    # Used by BillingService to generate monthly billing cycles
    monthly_rate:        float = Field(..., gt=0)
    deposit_multiplier:  float = Field(default=2.0, gt=0)  # deposit = rate * multiplier
    advance_multiplier:  float = Field(default=1.0, gt=0)  # advance = rate * multiplier

    @property
    def required_deposit(self) -> float:
        return round(self.monthly_rate * self.deposit_multiplier, 2)

    @property
    def required_advance(self) -> float:
        return round(self.monthly_rate * self.advance_multiplier, 2)

    @property
    def move_in_total(self) -> float:
        """Total amount required on move-in: deposit + advance + first month."""
        return round(self.required_deposit + self.required_advance + self.monthly_rate, 2)

    # ── Physical Details ──────────────────────────────────────
    dimension:  Optional[RoomDimension]  = None
    amenities:  list[RoomAmenity]        = Field(default_factory=list)

    # ── Media ─────────────────────────────────────────────────
    # List of image filepaths or URLs uploaded by admin
    images: list[str] = Field(default_factory=list)

    # ── Maintenance ───────────────────────────────────────────
    # Tracks the last time the room was inspected or repaired
    last_maintenance_date: Optional[datetime] = None
    maintenance_notes:     Optional[str]      = None

    # ── Ownership ─────────────────────────────────────────────
    # The manager who created this room. Used to scope the manager
    # dashboard so that each manager only sees their own rooms (and,
    # transitively, only their own tenants / leases / payments).
    #
    # Legacy rooms created before this field was introduced will have
    # manager_id == None. The repository's owner-filter falls back to
    # matching created_by == str(manager_id) for those records, which
    # works because manager_controller.create_room has always stored
    # str(current_user.id) in created_by.
    manager_id: Optional[PydanticObjectId] = None

    # ── Audit Fields ──────────────────────────────────────────
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None   
    updated_by: Optional[str] = None   # username of last editor

    # ── Beanie Settings ───────────────────────────────────────
    class Settings:
        name = "rooms"   # MongoDB collection name
        indexes = [
            [("room_number", 1)],   # fast lookup by room number (NOT unique
                                    # globally — uniqueness is enforced per
                                    # manager at the service layer so two
                                    # managers can each have their own "101").
            [("status", 1)],        # fast filter by status
            [("manager_id", 1)],    # fast filter for per-manager scoping
        ]

    # ── Computed Properties ───────────────────────────────────

    @property
    def is_vacant(self) -> bool:
        return self.status == RoomStatus.VACANT

    @property
    def is_occupied(self) -> bool:
        return self.status == RoomStatus.OCCUPIED

    @property
    def is_available(self) -> bool:
        """True if room can accept a new tenant."""
        return self.status == RoomStatus.VACANT

    @property
    def is_full(self) -> bool:
        """True if current occupants have reached max capacity."""
        return self.current_occupants >= self.max_occupants

    @property
    def has_amenity(self) -> bool:
        return len(self.amenities) > 0


    def __str__(self) -> str:
        return (
            f"Room("
            f"number={self.room_number}, "
            f"type={self.room_type.value}, "
            f"status={self.status.value}, "
            f"rate=₱{self.monthly_rate:,.2f}"
            f")"
        )

    def __repr__(self) -> str:
        return (
            f"<Room id={self.id} "
            f"number='{self.room_number}' "
            f"status='{self.status.value}'>"
        )