from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Main payment response ─────────────────────────────────────────────────────

class PaymentResponse(BaseModel):
    id:             str
    tenant_id:      str
    lease_id:       str
    room_id:        str
    recorded_by:    Optional[str] = None

    amount:         float
    type:           str
    method:         str
    status:         str

    reference_no:   Optional[str] = None
    notes:          Optional[str] = None

    receipt_number: Optional[str] = None
    receipt_url:    Optional[str] = None

    period_start:   Optional[datetime] = None
    period_end:     Optional[datetime] = None
    payment_date:   datetime
    confirmed_at:   Optional[datetime] = None

    # PayPal-specific fields (populated only for PayPal payments)
    paypal_order_id:   Optional[str] = None
    paypal_capture_id: Optional[str] = None
    paypal_payer_id:   Optional[str] = None
    paypal_payer_email: Optional[str] = None
    approval_url:      Optional[str] = None   # only in initiation response

    created_at:     datetime
    updated_at:     datetime

    @classmethod
    def from_payment(cls, payment) -> "PaymentResponse":
        return cls(
            id             = str(payment.id),
            tenant_id      = str(payment.tenant_id),
            lease_id       = str(payment.lease_id),
            room_id        = str(payment.room_id),
            recorded_by    = str(payment.recorded_by) if payment.recorded_by else None,
            amount         = payment.amount,
            type           = payment.type,
            method         = payment.method,
            status         = payment.status,
            reference_no   = payment.reference_no,
            notes          = payment.notes,
            receipt_number = payment.receipt_number,
            receipt_url    = payment.receipt_url,
            period_start   = payment.period_start,
            period_end     = payment.period_end,
            payment_date   = payment.payment_date,
            confirmed_at   = payment.confirmed_at,
            # PayPal extras stored in reference_no / receipt_url by convention
            # or as separate optional attrs added in PaymentService
            paypal_order_id    = getattr(payment, "paypal_order_id",    None),
            paypal_capture_id  = getattr(payment, "paypal_capture_id",  None),
            paypal_payer_id    = getattr(payment, "paypal_payer_id",    None),
            paypal_payer_email = getattr(payment, "paypal_payer_email", None),
            approval_url       = getattr(payment, "approval_url",       None),
            created_at     = payment.created_at,
            updated_at     = payment.updated_at,
        )


# ── PayPal initiation response (before capture) ───────────────────────────────

class PayPalInitResponse(BaseModel):
    """Returned immediately after POST /api/payments/paypal/initiate."""
    payment_id:       str     # internal MongoDB _id — pass back to /capture
    receipt_number:   str     # auto-generated RE-YYYYMMDD-XXXX
    order_id:         str     # PayPal order ID
    approval_url:     str     # redirect the tenant here
    amount:           float
    currency:         str = "PHP"


# ── Stats ─────────────────────────────────────────────────────────────────────

class PaymentStatsResponse(BaseModel):
    # ── Legacy fields (kept for backwards compatibility) ──────────────
    total_collected:  float
    total_pending:    float
    confirmed_count:  int
    pending_count:    int

    # ── New fields consumed by the manager dashboard / Payments tab ───
    # `paid_count`, `unpaid_count`, `partial_count` drive the
    # "X paid · Y unpaid · Z partial" header. `total_outstanding`
    # is the headline "Outstanding" stat card. `monthly_revenue`
    # is the current-month total of confirmed payments.
    total_payments:     Optional[int]   = 0
    paid_count:         Optional[int]   = 0
    unpaid_count:       Optional[int]   = 0
    partial_count:      Optional[int]   = 0
    total_outstanding:  Optional[float] = 0.0
    monthly_revenue:    Optional[float] = 0.0
    monthly_collected:  Optional[float] = 0.0


# ── Paginated list (kept simple — service returns plain list today) ────────────

class PaymentListResponse(BaseModel):
    total:    int
    payments: List[PaymentResponse]
