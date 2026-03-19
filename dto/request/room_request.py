
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional

from models.room import RoomType, FloorLevel


# ================================================================
# EMBEDDED REQUEST SCHEMAS
# ================================================================

class RoomDimensionRequest(BaseModel):
    """
    Physical dimensions of the room.
    Both fields are optional — can provide one or both.
    """
    length_sqm: Optional[float] = Field(default=None, gt=0)
    width_sqm:  Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def at_least_one_dimension(self) -> "RoomDimensionRequest":
        if self.length_sqm is None and self.width_sqm is None:
            raise ValueError(
                "Provide at least one dimension: length_sqm or width_sqm."
            )
        return self


class RoomAmenityRequest(BaseModel):
    """
    An amenity included in the room.
    e.g. aircon, wifi, private bathroom, ref, water heater
    """
    name:        str            = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    is_working:  bool          = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


# ================================================================
# ROOM CREATE REQUEST
# ================================================================

class RoomCreateRequest(BaseModel):
    """
    Payload for POST /api/rooms

    Required:
    - room_number   → must be unique across all rooms
    - room_type     → SINGLE, DOUBLE, STUDIO, DORMITORY, SUITE
    - monthly_rate  → base rent in PHP, must be > 0

    Optional:
    - floor_level, description, max_occupants
    - deposit_multiplier, advance_multiplier
    - dimension, amenities
    """

    # ── Room Identity ─────────────────────────────────────────
    room_number:  str                  = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Unique room identifier e.g. '101', '2A', 'GF-03'"
    )
    floor_level:  Optional[FloorLevel] = None
    room_type:    RoomType             = RoomType.SINGLE
    description:  Optional[str]        = Field(default=None, max_length=500)

    # ── Capacity ──────────────────────────────────────────────
    max_occupants: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Maximum number of tenants allowed in this room."
    )

    # ── Financial ─────────────────────────────────────────────
    monthly_rate: float = Field(
        ...,
        gt=0,
        description="Base monthly rent in PHP."
    )
    deposit_multiplier: float = Field(
        default=2.0,
        gt=0,
        description="Security deposit = monthly_rate × deposit_multiplier."
    )
    advance_multiplier: float = Field(
        default=1.0,
        gt=0,
        description="Advance payment = monthly_rate × advance_multiplier."
    )

    # ── Physical Details ──────────────────────────────────────
    dimension:  Optional[RoomDimensionRequest]  = None
    amenities:  list[RoomAmenityRequest]        = Field(default_factory=list)

    # ── Validators ────────────────────────────────────────────

    @field_validator("room_number")
    @classmethod
    def strip_and_upper_room_number(cls, v: str) -> str:
        """Strips whitespace and uppercases room number for consistency."""
        return v.strip().upper()

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None

    @field_validator("monthly_rate", "deposit_multiplier", "advance_multiplier")
    @classmethod
    def round_to_two_decimals(cls, v: float) -> float:
        return round(v, 2)

    @model_validator(mode="after")
    def validate_max_occupants_vs_type(self) -> "RoomCreateRequest":
        """
        Validates that max_occupants is consistent with room type.
        SINGLE should not allow more than 1 occupant.
        DORMITORY should allow more than 2.
        """
        if self.room_type == RoomType.SINGLE and self.max_occupants > 1:
            raise ValueError(
                "SINGLE room type should have max_occupants of 1. "
                "Use DOUBLE or DORMITORY for multiple occupants."
            )
        if self.room_type == RoomType.DOUBLE and self.max_occupants > 2:
            raise ValueError(
                "DOUBLE room type should have max_occupants of 2. "
                "Use DORMITORY for more than 2 occupants."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "room_number":          "101",
                "floor_level":          "GROUND",
                "room_type":            "SINGLE",
                "description":          "Ground floor single room with private bathroom.",
                "max_occupants":        1,
                "monthly_rate":         5000.00,
                "deposit_multiplier":   2.0,
                "advance_multiplier":   1.0,
                "dimension": {
                    "length_sqm": 4.0,
                    "width_sqm":  3.5
                },
                "amenities": [
                    {
                        "name":        "Aircon",
                        "description": "1.0 HP window type aircon",
                        "is_working":  True
                    },
                    {
                        "name":        "WiFi",
                        "description": "Shared fiber internet connection",
                        "is_working":  True
                    }
                ]
            }
        }
    }


# ================================================================
# ROOM UPDATE REQUEST
# ================================================================

class RoomUpdateRequest(BaseModel):
    """
    Payload for PATCH /api/rooms/{room_id}

    All fields are optional — only fields included in the
    request body will be updated (true PATCH behavior).
    Omitting a field means 'leave it unchanged', not 'set to null'.

    Note: status is NOT updatable here.
    Use PATCH /api/rooms/{room_id}/status for status changes.
    """

    # ── Room Identity ─────────────────────────────────────────
    room_number:  Optional[str]        = Field(default=None, min_length=1, max_length=20)
    floor_level:  Optional[FloorLevel] = None
    room_type:    Optional[RoomType]   = None
    description:  Optional[str]        = Field(default=None, max_length=500)

    # ── Capacity ──────────────────────────────────────────────
    max_occupants: Optional[int] = Field(default=None, ge=1, le=20)

    # ── Financial ─────────────────────────────────────────────
    monthly_rate:        Optional[float] = Field(default=None, gt=0)
    deposit_multiplier:  Optional[float] = Field(default=None, gt=0)
    advance_multiplier:  Optional[float] = Field(default=None, gt=0)

    # ── Physical Details ──────────────────────────────────────
    dimension:  Optional[RoomDimensionRequest]   = None
    amenities:  Optional[list[RoomAmenityRequest]] = None

    # ── Validators ────────────────────────────────────────────

    @field_validator("room_number")
    @classmethod
    def strip_and_upper_room_number(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else None

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None

    @field_validator("monthly_rate", "deposit_multiplier", "advance_multiplier")
    @classmethod
    def round_to_two_decimals(cls, v: Optional[float]) -> Optional[float]:
        return round(v, 2) if v is not None else None

    @model_validator(mode="after")
    def at_least_one_field_required(self) -> "RoomUpdateRequest":
        provided = {
            k: v for k, v in self.model_dump().items()
            if v is not None
        }
        if not provided:
            raise ValueError(
                "At least one field must be provided for update."
            )
        return self

    @model_validator(mode="after")
    def validate_max_occupants_vs_type(self) -> "RoomUpdateRequest":
        """
        Only validates if BOTH room_type and max_occupants are provided.
        If only one is provided, the service layer handles consistency.
        """
        if self.room_type and self.max_occupants:
            if self.room_type == RoomType.SINGLE and self.max_occupants > 1:
                raise ValueError(
                    "SINGLE room type should have max_occupants of 1."
                )
            if self.room_type == RoomType.DOUBLE and self.max_occupants > 2:
                raise ValueError(
                    "DOUBLE room type should have max_occupants of 2."
                )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "monthly_rate": 5500.00,
                "description":  "Newly renovated with fresh paint.",
                "amenities": [
                    {
                        "name":        "Aircon",
                        "description": "1.5 HP split type aircon",
                        "is_working":  True
                    }
                ]
            }
        }
    }


# ================================================================
# MAINTENANCE REQUEST BODY
# ================================================================

class MaintenanceStartRequest(BaseModel):
    """
    Payload for PATCH /api/rooms/{room_id}/maintenance/start
    """
    maintenance_notes: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Description of the maintenance work to be done."
    )

    @field_validator("maintenance_notes")
    @classmethod
    def strip_notes(cls, v: str) -> str:
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "maintenance_notes": "Aircon unit not cooling properly. "
                                     "Technician scheduled for repair."
            }
        }
    }


# ================================================================
# ROOM IMAGE REQUEST
# ================================================================

class RoomImageRequest(BaseModel):
    """
    Payload for POST /api/rooms/{room_id}/images
    and DELETE /api/rooms/{room_id}/images
    """
    image_url: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Filepath or URL of the room image."
    )

    @field_validator("image_url")
    @classmethod
    def strip_and_validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://", "/uploads/", "uploads/")):
            raise ValueError(
                "image_url must be a valid URL or an uploads/ filepath."
            )
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "image_url": "https://res.cloudinary.com/residease/rooms/room101.jpg"
            }
        }
    }