
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.room import RoomType, RoomStatus
from models.lease import LeaseStatus
from models.payment import PaymentMethod, PaymentType, PaymentStatus
from models.maintenance import MaintenanceCategory, MaintenancePriority, MaintenanceStatus


# ── Room requests ─────────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    room_number:  str         = Field(..., min_length=1, max_length=10)
    monthly_rent: float       = Field(..., gt=0)
    room_type:    RoomType    = RoomType.SINGLE
    capacity:     int         = Field(default=1, ge=1, le=10)
    floor:        Optional[int]   = None
    wing:         Optional[str]   = None
    deposit:      float           = Field(default=0.0, ge=0)
    amenities:    list[str]       = Field(default_factory=list)
    description:  Optional[str]   = Field(default=None, max_length=1000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "room_number": "2A",
                "monthly_rent": 4500.00,
                "room_type": "SINGLE",
                "capacity": 1,
                "floor": 2,
                "wing": "North",
                "deposit": 4500.00,
                "amenities": ["WiFi", "AC", "Own CR"],
                "description": "Quiet room on the 2nd floor."
            }
        }
    }


class UpdateRoomRequest(BaseModel):
    room_number:  Optional[str]       = None
    monthly_rent: Optional[float]     = Field(default=None, gt=0)
    room_type:    Optional[RoomType]  = None
    capacity:     Optional[int]       = Field(default=None, ge=1, le=10)
    floor:        Optional[int]       = None
    wing:         Optional[str]       = None
    deposit:      Optional[float]     = Field(default=None, ge=0)
    amenities:    Optional[list[str]] = None
    description:  Optional[str]       = None
    status:       Optional[RoomStatus] = None


class UpdateRoomStatusRequest(BaseModel):
    status: RoomStatus


# ── Lease requests ────────────────────────────────────────────────────────────

class CreateLeaseRequest(BaseModel):
    tenant_id:      str
    tenant_user_id: str
    room_id:        str
    start_date:     datetime
    end_date:       Optional[datetime] = None
    monthly_rent:   float              = Field(..., gt=0)
    deposit_amount: float              = Field(default=0.0, ge=0)
    billing_day:    int                = Field(default=1, ge=1, le=28)
    notes:          Optional[str]      = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id":      "665f1c2e8a4b2c001f3d9a11",
                "tenant_user_id": "665f1c2e8a4b2c001f3d9a00",
                "room_id":        "665f1c2e8a4b2c001f3d9b22",
                "start_date":     "2026-05-01T00:00:00",
                "end_date":       "2027-04-30T00:00:00",
                "monthly_rent":   4500.00,
                "deposit_amount": 4500.00,
                "billing_day":    1,
            }
        }
    }


class TerminateLeaseRequest(BaseModel):
    move_out_date: Optional[datetime] = None
    notes:         Optional[str]      = None


class RenewLeaseRequest(BaseModel):
    new_end_date: datetime
    new_rent:     Optional[float] = Field(default=None, gt=0)


# ── Payment requests ──────────────────────────────────────────────────────────

class RecordPaymentRequest(BaseModel):
    tenant_id:    str
    lease_id:     str
    room_id:      str
    amount:       float              = Field(..., gt=0)
    method:       PaymentMethod      = PaymentMethod.CASH
    type:         PaymentType        = PaymentType.RENT
    reference_no: Optional[str]      = None
    notes:        Optional[str]      = None
    period_start: Optional[datetime] = None
    period_end:   Optional[datetime] = None

    # When set, controls how the payment row is created:
    #   - CONFIRMED  (default): manager is recording money already received
    #                           ("+ Record Payment" from the Payments tab).
    #   - PENDING:              manager is assigning a charge that the tenant
    #                           still has to pay ("+ Assign Payment" from the
    #                           Leases tab). Increases lease.outstanding_balance.
    status:       Optional[PaymentStatus] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id":    "665f1c2e8a4b2c001f3d9a11",
                "lease_id":     "665f1c2e8a4b2c001f3d9c33",
                "room_id":      "665f1c2e8a4b2c001f3d9b22",
                "amount":       4500.00,
                "method":       "GCASH",
                "type":         "RENT",
                "reference_no": "GC-20260501-1234",
                "period_start": "2026-05-01T00:00:00",
                "period_end":   "2026-05-31T00:00:00",
            }
        }
    }


# ── Maintenance requests ──────────────────────────────────────────────────────

class SubmitMaintenanceRequest(BaseModel):
    tenant_id:   str
    room_id:     str
    title:       str               = Field(..., min_length=3, max_length=200)
    description: str               = Field(..., min_length=10, max_length=2000)
    category:    MaintenanceCategory = MaintenanceCategory.OTHER
    priority:    MaintenancePriority = MaintenancePriority.MEDIUM
    photos:      list[str]           = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id":   "665f1c2e8a4b2c001f3d9a11",
                "room_id":     "665f1c2e8a4b2c001f3d9b22",
                "title":       "Leaking faucet",
                "description": "The faucet in the comfort room has been leaking since yesterday.",
                "category":    "PLUMBING",
                "priority":    "HIGH",
            }
        }
    }


class AssignMaintenanceRequest(BaseModel):
    assigned_to: str    # User._id of the maintenance staff


class CompleteMaintenanceRequest(BaseModel):
    resolution: str = Field(..., min_length=5, max_length=1000)


class RejectMaintenanceRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=5, max_length=500)
