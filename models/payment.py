from beanie import Document, PydanticObjectId
from pydantic import Field
from typing import Optional
from datetime import datetime
from enum import Enum


class PaymentMethod(str, Enum):
    CASH          = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    GCASH         = "GCASH"
    PAYMAYA       = "PAYMAYA"
    CARD          = "CARD"
    PAYPAL        = "PAYPAL"
    OTHER         = "OTHER"


class PaymentStatus(str, Enum):
    PENDING   = "PENDING"
    CONFIRMED = "CONFIRMED"
    PARTIAL   = "PARTIAL"
    FAILED    = "FAILED"
    REFUNDED  = "REFUNDED"


class PaymentType(str, Enum):
    RENT          = "RENT"
    DEPOSIT       = "DEPOSIT"
    ADVANCE       = "ADVANCE"
    PENALTY       = "PENALTY"
    UTILITY       = "UTILITY"
    OTHER         = "OTHER"


class Payment(Document):
    """
    A single payment transaction.
    Collection: payments
    """

    # ── Participants ──────────────────────────────────────────────────────
    tenant_id:      PydanticObjectId
    lease_id:       PydanticObjectId
    room_id:        PydanticObjectId
    recorded_by:    Optional[PydanticObjectId] = None   # manager who recorded it

    # ── Amount ────────────────────────────────────────────────────────────
    amount:         float           = Field(..., gt=0)
    type:           PaymentType     = PaymentType.RENT

    # ── Period this payment covers ────────────────────────────────────────
    period_start:   Optional[datetime] = None    # e.g. April 1, 2026
    period_end:     Optional[datetime] = None    # e.g. April 30, 2026

    # ── PayPal-specific tracking ──────────────────────────────────────────
    # These are written by PaymentService.capture_paypal_payment() after a
    # successful capture. They must exist as schema fields or Pydantic v2
    # will reject the attribute assignment and the capture endpoint will 500.
    paypal_order_id:    Optional[str] = None
    paypal_capture_id:  Optional[str] = None
    paypal_payer_id:    Optional[str] = None
    paypal_payer_email: Optional[str] = None

    # ── Payment details ───────────────────────────────────────────────────
    method:         PaymentMethod   = PaymentMethod.CASH
    status:         PaymentStatus   = PaymentStatus.PENDING
    reference_no:   Optional[str]   = None  # GCash ref, bank transfer ref, etc.
    notes:          Optional[str]   = Field(default=None, max_length=500)

    # ── Receipt ───────────────────────────────────────────────────────────
    receipt_number: Optional[str]   = None  # auto-generated receipt number
    receipt_url:    Optional[str]   = None  # PDF receipt path/URL

    # ── Dates ─────────────────────────────────────────────────────────────
    payment_date:   datetime        = Field(default_factory=datetime.utcnow)
    confirmed_at:   Optional[datetime] = None

    # ── Audit ─────────────────────────────────────────────────────────────
    created_at:     datetime        = Field(default_factory=datetime.utcnow)
    updated_at:     datetime        = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payments"
