# ============================================================
# dto/response/room_response.py
# ResidEase – Boarding House Management System
# ============================================================

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from models.room import Room, RoomStatus, RoomType, FloorLevel


# ================================================================
# EMBEDDED RESPONSE SCHEMAS
# ================================================================

class RoomDimensionResponse(BaseModel):
    """
    Physical dimensions returned in room responses.
    """
    length_sqm: Optional[float] = None
    width_sqm:  Optional[float] = None
    area_sqm:   Optional[float] = None   # computed: length × width


class RoomAmenityResponse(BaseModel):
    """
    Single amenity returned in room responses.
    """
    name:        str
    description: Optional[str] = None
    is_working:  bool


# ================================================================
# MAIN ROOM RESPONSE
# ================================================================

class RoomResponse(BaseModel):
    """
    Full room data returned by all room endpoints.
    Consistent shape across GET, POST, PATCH responses.
    """

    # ── Identity ──────────────────────────────────────────────
    id:           str
    room_number:  str
    floor_level:  Optional[FloorLevel] = None
    room_type:    RoomType
    description:  Optional[str]        = None

    # ── Capacity ──────────────────────────────────────────────
    max_occupants:     int
    current_occupants: int

    # ── Status ────────────────────────────────────────────────
    status:      RoomStatus
    is_vacant:   bool
    is_occupied: bool
    is_full:     bool

    # ── Financial ─────────────────────────────────────────────
    monthly_rate:       float
    deposit_multiplier: float
    advance_multiplier: float
    required_deposit:   float   # monthly_rate × deposit_multiplier
    required_advance:   float   # monthly_rate × advance_multiplier
    move_in_total:      float   # deposit + advance + first month

    # ── Physical Details ──────────────────────────────────────
    dimension:  Optional[RoomDimensionResponse]  = None
    amenities:  list[RoomAmenityResponse]        = []

    # ── Media ─────────────────────────────────────────────────
    images: list[str] = []

    # ── Maintenance ───────────────────────────────────────────
    last_maintenance_date: Optional[datetime] = None
    maintenance_notes:     Optional[str]      = None

    # ── Audit ─────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    # ── Factory Method ────────────────────────────────────────

    @classmethod
    def from_room(cls, room: Room) -> "RoomResponse":
        """
        Constructs a RoomResponse from a Room Beanie document.
        Called by room_service.py — never construct this manually.

        Computed properties (is_vacant, required_deposit, etc.)
        are evaluated here from the Room model's @property methods.
        """

        # ── Dimension ─────────────────────────────────────────
        dimension_response = None
        if room.dimension:
            dimension_response = RoomDimensionResponse(
                length_sqm=room.dimension.length_sqm,
                width_sqm=room.dimension.width_sqm,
                area_sqm=room.dimension.area_sqm,
            )

        # ── Amenities ─────────────────────────────────────────
        amenity_responses = [
            RoomAmenityResponse(
                name=a.name,
                description=a.description,
                is_working=a.is_working,
            )
            for a in room.amenities
        ]

        return cls(
            # Identity
            id=str(room.id),
            room_number=room.room_number,
            floor_level=room.floor_level,
            room_type=room.room_type,
            description=room.description,

            # Capacity
            max_occupants=room.max_occupants,
            current_occupants=room.current_occupants,

            # Status — computed from @property
            status=room.status,
            is_vacant=room.is_vacant,
            is_occupied=room.is_occupied,
            is_full=room.is_full,

            # Financial — computed from @property
            monthly_rate=room.monthly_rate,
            deposit_multiplier=room.deposit_multiplier,
            advance_multiplier=room.advance_multiplier,
            required_deposit=room.required_deposit,
            required_advance=room.required_advance,
            move_in_total=room.move_in_total,

            # Physical
            dimension=dimension_response,
            amenities=amenity_responses,

            # Media
            images=room.images,

            # Maintenance
            last_maintenance_date=room.last_maintenance_date,
            maintenance_notes=room.maintenance_notes,

            # Audit
            created_at=room.created_at,
            updated_at=room.updated_at,
            created_by=room.created_by,
            updated_by=room.updated_by,
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id":                    "665f1c2e8a4b2c001f3d9b22",
                "room_number":           "101",
                "floor_level":           "GROUND",
                "room_type":             "SINGLE",
                "description":           "Ground floor single room with private bathroom.",
                "max_occupants":         1,
                "current_occupants":     0,
                "status":                "VACANT",
                "is_vacant":             True,
                "is_occupied":           False,
                "is_full":               False,
                "monthly_rate":          5000.00,
                "deposit_multiplier":    2.0,
                "advance_multiplier":    1.0,
                "required_deposit":      10000.00,
                "required_advance":      5000.00,
                "move_in_total":         20000.00,
                "dimension": {
                    "length_sqm":        4.0,
                    "width_sqm":         3.5,
                    "area_sqm":          14.0
                },
                "amenities": [
                    {
                        "name":          "Aircon",
                        "description":   "1.0 HP window type aircon",
                        "is_working":    True
                    },
                    {
                        "name":          "WiFi",
                        "description":   "Shared fiber internet connection",
                        "is_working":    True
                    }
                ],
                "images": [
                    "https://res.cloudinary.com/residease/rooms/room101_1.jpg",
                    "https://res.cloudinary.com/residease/rooms/room101_2.jpg"
                ],
                "last_maintenance_date": None,
                "maintenance_notes":     None,
                "created_at":            "2024-06-01T08:00:00",
                "updated_at":            "2024-06-01T08:00:00",
                "created_by":            "admin_user",
                "updated_by":            "admin_user"
            }
        }
    }


# ================================================================
# ROOM SUMMARY RESPONSE  (lightweight — for dropdowns / listings)
# ================================================================

class RoomSummaryResponse(BaseModel):
    """
    Lightweight room shape used in:
    - Tenant profile (showing assigned room)
    - Lease response (showing room details)
    - Room selection dropdowns in the frontend

    Does NOT include amenities, images, audit fields, or financials.
    Use RoomResponse for full detail views.
    """
    id:           str
    room_number:  str
    floor_level:  Optional[FloorLevel] = None
    room_type:    RoomType
    status:       RoomStatus
    monthly_rate: float
    is_vacant:    bool
    is_full:      bool

    @classmethod
    def from_room(cls, room: Room) -> "RoomSummaryResponse":
        return cls(
            id=str(room.id),
            room_number=room.room_number,
            floor_level=room.floor_level,
            room_type=room.room_type,
            status=room.status,
            monthly_rate=room.monthly_rate,
            is_vacant=room.is_vacant,
            is_full=room.is_full,
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id":           "665f1c2e8a4b2c001f3d9b22",
                "room_number":  "101",
                "floor_level":  "GROUND",
                "room_type":    "SINGLE",
                "status":       "VACANT",
                "monthly_rate": 5000.00,
                "is_vacant":    True,
                "is_full":      False
            }
        }
    }