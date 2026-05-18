"""
services/payment_service.py

Extends the existing PaymentService with PayPal REST API v2 support.
All existing methods are preserved unchanged.

PayPal flow:
  1. POST /api/payments/paypal/initiate
       → creates PayPal order, saves PENDING Payment, returns approval_url
  2. Tenant approves on PayPal redirect page
  3. POST /api/payments/paypal/capture
       → captures the order, confirms the Payment, notifies tenant
"""

import uuid
import base64
import httpx
from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from fastapi import HTTPException

from models.payment import Payment, PaymentStatus, PaymentMethod, PaymentType
from repository import payment_repository
from repository import lease_repository
from repository.notification_repository import create_notification
from models.notification import NotificationType
from config.payment_gateway_config import paypal_cfg
from dto.request.payment_request import (
    CashPaymentRequest,
    PayPalPaymentRequest,
    PayPalCaptureRequest,
)
from dto.response.payment_response import (
    PaymentResponse,
    PayPalInitResponse,
    PaymentStatsResponse,
    PaymentListResponse,
)


# ═══════════════════════════════════════════════════════════════
#  PAYPAL HELPERS  (module-level, not on the class)
# ═══════════════════════════════════════════════════════════════

async def _get_paypal_access_token() -> str:
    """Exchange client_id:secret for a short-lived Bearer token."""
    credentials = base64.b64encode(
        f"{paypal_cfg.client_id}:{paypal_cfg.secret_key}".encode()
    ).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{paypal_cfg.base_url}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"PayPal auth failed: {resp.text}")
    return resp.json()["access_token"]


async def _paypal_headers() -> dict:
    token = await _get_paypal_access_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _find_approval_url(links: list) -> Optional[str]:
    for link in links:
        if link.get("rel") == "approve":
            return link["href"]
    return None


# ═══════════════════════════════════════════════════════════════
#  SERVICE
# ═══════════════════════════════════════════════════════════════

class PaymentService:

    # ─────────────────────────────────────────────────────────────
    #  Helpers (kept from original)
    # ─────────────────────────────────────────────────────────────

    def _generate_receipt_number(self) -> str:
        date_part = datetime.utcnow().strftime("%Y%m%d")
        rand_part = uuid.uuid4().hex[:4].upper()
        return f"RE-{date_part}-{rand_part}"

    async def _notify_tenant(
        self,
        lease_id:      str,
        title:         str,
        message:       str,
        reference_id:  str,
    ) -> None:
        """Fire-and-forget notification — failure never blocks the payment."""
        try:
            lease = await lease_repository.get_lease_by_id(PydanticObjectId(lease_id))
            if lease and hasattr(lease, "tenant_user_id"):
                await create_notification(
                    user_id        = str(lease.tenant_user_id),
                    type           = NotificationType.PAYMENT_RECEIVED,
                    title          = title,
                    message        = message,
                    reference_id   = reference_id,
                    reference_type = "payment",
                )
        except Exception:
            pass

    async def _apply_balance_change(
        self,
        lease_id: str,
        amount:   float,
        action:   str,  # "charge" | "settle" | "reverse_charge"
    ) -> None:
        """
        Keep `lease.outstanding_balance` and `lease.total_paid` in sync with
        the payment-row lifecycle so the Outstanding card and Unpaid count
        on the manager dashboard always reflect reality.

        action:
          - "charge":          a new PENDING (Assign Payment) row was created.
                               Increases outstanding_balance.
          - "settle":          a payment row became CONFIRMED (either created
                               CONFIRMED directly, or transitioned
                               PENDING -> CONFIRMED via confirm / PayPal
                               capture). Decreases outstanding_balance
                               (clamped to >= 0) and increases total_paid.
          - "reverse_charge":  a PENDING payment row was deleted. Decreases
                               outstanding_balance (clamped to >= 0).

        All errors are swallowed and logged — the payment itself must never
        be blocked because the lease totals failed to update.
        """
        try:
            lease = await lease_repository.get_lease_by_id(
                PydanticObjectId(lease_id)
            )
            if not lease:
                return

            current_outstanding = float(getattr(lease, "outstanding_balance", 0.0) or 0.0)
            current_paid        = float(getattr(lease, "total_paid",          0.0) or 0.0)

            if action == "charge":
                new_outstanding = current_outstanding + amount
                new_paid        = current_paid
            elif action == "settle":
                new_outstanding = max(0.0, current_outstanding - amount)
                new_paid        = current_paid + amount
            elif action == "reverse_charge":
                new_outstanding = max(0.0, current_outstanding - amount)
                new_paid        = current_paid
            else:
                return

            lease.outstanding_balance = round(new_outstanding, 2)
            lease.total_paid          = round(new_paid,        2)
            lease.updated_at          = datetime.utcnow()
            await lease.save()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to apply lease balance change (%s, %s, %s): %s",
                lease_id, amount, action, exc,
            )

    # ─────────────────────────────────────────────────────────────
    #  Original read methods (unchanged)
    # ─────────────────────────────────────────────────────────────

    async def get_all_payments(self) -> list[Payment]:
        return await payment_repository.get_all_payments()

    async def get_payment_by_id(self, payment_id: str) -> Payment:
        payment = await payment_repository.find_payment_by_id(payment_id)
        if not payment:
            raise HTTPException(404, "Payment not found.")
        return payment

    async def get_tenant_payments(self, tenant_id: str) -> list[Payment]:
        return await payment_repository.find_payments_by_tenant(tenant_id)

    async def get_lease_payments(self, lease_id: str) -> list[Payment]:
        return await payment_repository.find_payments_by_lease(lease_id)

    async def get_payment_stats(self) -> PaymentStatsResponse:
        """
        Compute headline payment statistics for the manager dashboard.

        Returned shape matches the frontend `PaymentStats` interface:
          - total_payments, paid_count, unpaid_count, partial_count
          - total_collected, total_outstanding
          - monthly_revenue, monthly_collected

        `total_outstanding` is the sum of `lease.outstanding_balance`
        across every ACTIVE lease. Each PENDING payment row (Assigned
        Payment / un-captured PayPal order) has already incremented its
        lease's outstanding_balance via `_apply_balance_change`, so we
        do NOT also sum PENDING payment amounts here — that would
        double-count.

        Guard: any Payment with amount=None is treated as 0 so a single
        malformed document never crashes the whole stats endpoint.
        """
        # Local import to avoid a circular import at module load time.
        from repository import lease_repository
        from models.lease import LeaseStatus

        all_payments = await payment_repository.get_all_payments()

        confirmed = [p for p in all_payments if p.status == PaymentStatus.CONFIRMED]
        pending   = [p for p in all_payments if p.status == PaymentStatus.PENDING]
        partial   = [p for p in all_payments if p.status == PaymentStatus.PARTIAL]
        failed    = [p for p in all_payments if p.status == PaymentStatus.FAILED]

        # Monthly figures — payments confirmed in the current calendar month
        now = datetime.utcnow()
        monthly_confirmed = [
            p for p in confirmed
            if p.confirmed_at
            and p.confirmed_at.year  == now.year
            and p.confirmed_at.month == now.month
        ]

        def safe_sum(payments) -> float:
            """Sum amounts, skipping any None values from malformed records."""
            return sum(p.amount or 0.0 for p in payments)

        # Pull outstanding balances directly from ACTIVE leases so balances
        # accrued by the rent scheduler still count even without a payment row.
        try:
            active_leases = await lease_repository.get_leases_by_status(
                LeaseStatus.ACTIVE
            )
        except Exception:
            # Fallback if repository signature differs — never fail the stats.
            from models.lease import Lease as _Lease
            active_leases = await _Lease.find(_Lease.status == LeaseStatus.ACTIVE).to_list()

        # Outstanding = sum of lease.outstanding_balance across active leases.
        # PENDING payment amounts are already reflected here (each PENDING
        # row bumped its lease via _apply_balance_change), so we don't sum
        # them again.
        total_outstanding = sum(
            (getattr(l, "outstanding_balance", 0.0) or 0.0)
            for l in active_leases
        )
        total_collected   = safe_sum(confirmed)
        monthly_collected = safe_sum(monthly_confirmed)

        return PaymentStatsResponse(
            # legacy
            total_collected = total_collected,
            total_pending   = safe_sum(pending),
            confirmed_count = len(confirmed),
            pending_count   = len(pending),
            # new
            total_payments    = len(all_payments),
            paid_count        = len(confirmed),
            unpaid_count      = len(pending),
            partial_count     = len(partial),
            total_outstanding = total_outstanding,
            monthly_revenue   = monthly_collected,
            monthly_collected = monthly_collected,
        )

    # ─────────────────────────────────────────────────────────────
    #  Original write methods (unchanged, just wrapped in DTO)
    # ─────────────────────────────────────────────────────────────

    async def record_payment(
        self,
        tenant_id:    str,
        lease_id:     str,
        room_id:      str,
        amount:       float,
        method:       PaymentMethod   = PaymentMethod.CASH,
        type:         PaymentType     = PaymentType.RENT,
        reference_no: str | None      = None,
        notes:        str | None      = None,
        period_start: datetime | None = None,
        period_end:   datetime | None = None,
        recorded_by:  str | None      = None,
        status:       PaymentStatus   = PaymentStatus.CONFIRMED,
    ) -> Payment:
        """
        Create a payment row.

        Two distinct flows feed this:

        - **Record Payment** (default, status=CONFIRMED): the manager is
          recording money that has actually been received. The payment is
          marked CONFIRMED on creation; `lease.total_paid` is incremented
          and `lease.outstanding_balance` is reduced (clamped >= 0).

        - **Assign Payment** (status=PENDING): the manager is creating an
          invoice / charge the tenant still has to pay. The payment row is
          PENDING, the tenant can later settle it via PayPal capture or by
          the manager confirming it. `lease.outstanding_balance` is bumped
          up so the Outstanding card on the dashboard reflects the new
          debt immediately.

        PayPal flows go through `initiate_paypal_payment` /
        `capture_paypal_payment_by_token` instead.
        """
        now = datetime.utcnow()
        is_confirmed = status == PaymentStatus.CONFIRMED

        payment = Payment(
            tenant_id      = PydanticObjectId(tenant_id),
            lease_id       = PydanticObjectId(lease_id),
            room_id        = PydanticObjectId(room_id),
            amount         = amount,
            method         = method,
            type           = type,
            status         = status,
            reference_no   = reference_no,
            notes          = notes,
            period_start   = period_start,
            period_end     = period_end,
            recorded_by    = PydanticObjectId(recorded_by) if recorded_by else None,
            receipt_number = self._generate_receipt_number(),
            confirmed_at   = now if is_confirmed else None,
        )
        saved = await payment_repository.save_payment(payment)

        # Keep lease balances in sync
        await self._apply_balance_change(
            lease_id = lease_id,
            amount   = amount,
            action   = "settle" if is_confirmed else "charge",
        )

        if is_confirmed:
            title   = "Payment received"
            message = f"Your payment of ₱{amount:,.2f} has been received and confirmed."
        else:
            title   = "New charge assigned"
            message = (
                f"A new {type.value.lower()} charge of ₱{amount:,.2f} has been "
                f"assigned to your lease. Please settle this balance to avoid penalties."
            )
        await self._notify_tenant(
            lease_id     = lease_id,
            title        = title,
            message      = message,
            reference_id = str(saved.id),
        )
        return saved

    async def confirm_payment(self, payment_id: str) -> Payment:
        payment = await self.get_payment_by_id(payment_id)
        if payment.status == PaymentStatus.CONFIRMED:
            raise HTTPException(400, "Payment is already confirmed.")

        payment.status       = PaymentStatus.CONFIRMED
        payment.confirmed_at = datetime.utcnow()
        payment.updated_at   = datetime.utcnow()
        saved = await payment_repository.save_payment(payment)

        # Transition PENDING (charge) -> CONFIRMED (settled).
        # `settle` bumps total_paid and decrements outstanding_balance.
        await self._apply_balance_change(
            lease_id = str(payment.lease_id),
            amount   = float(payment.amount or 0.0),
            action   = "settle",
        )
        return saved

    async def delete_payment(self, payment_id: str) -> dict:
        payment = await self.get_payment_by_id(payment_id)
        if payment.status == PaymentStatus.CONFIRMED:
            raise HTTPException(400, "Cannot delete a confirmed payment.")

        # Deleting a PENDING charge has to reverse the outstanding bump
        # the original `record_payment(... status=PENDING)` applied.
        if payment.status == PaymentStatus.PENDING:
            await self._apply_balance_change(
                lease_id = str(payment.lease_id),
                amount   = float(payment.amount or 0.0),
                action   = "reverse_charge",
            )

        await payment_repository.delete_payment(payment)
        return {"message": "Payment deleted."}

    # ─────────────────────────────────────────────────────────────
    #  NEW — Cash payment via DTO (controller convenience)
    # ─────────────────────────────────────────────────────────────

    async def record_cash_payment(
        self, data: CashPaymentRequest, recorded_by: str
    ) -> PaymentResponse:
        saved = await self.record_payment(
            tenant_id    = data.tenant_id,
            lease_id     = data.lease_id,
            room_id      = data.room_id,
            amount       = data.amount,
            method       = data.method,
            type         = data.type,
            reference_no = data.reference_no,
            notes        = data.notes,
            period_start = data.period_start,
            period_end   = data.period_end,
            recorded_by  = recorded_by,
        )
        return PaymentResponse.from_payment(saved)

    # ─────────────────────────────────────────────────────────────
    #  NEW — PayPal: initiate (create order)
    # ─────────────────────────────────────────────────────────────

    async def initiate_paypal_payment(
        self, data: PayPalPaymentRequest, recorded_by: str
    ) -> PayPalInitResponse:
        receipt_number = self._generate_receipt_number()
        headers        = await _paypal_headers()

        order_payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": receipt_number,
                "description":  f"ResidEase {data.type} – {receipt_number}",
                "amount": {
                    "currency_code": paypal_cfg.currency,
                    "value":         f"{data.amount:.2f}",
                },
            }],
            "application_context": {
                "brand_name":  "ResidEase",
                "landing_page": "BILLING",
                "user_action":  "PAY_NOW",
                "return_url":   f"{paypal_cfg.return_url}?ref={receipt_number}",
                "cancel_url":   paypal_cfg.cancel_url,
            },
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{paypal_cfg.base_url}/v2/checkout/orders",
                headers=headers,
                json=order_payload,
            )
        if resp.status_code not in (200, 201):
            raise HTTPException(502, f"PayPal order creation failed: {resp.text}")

        order_data   = resp.json()
        order_id     = order_data["id"]
        approval_url = _find_approval_url(order_data.get("links", []))
        if not approval_url:
            raise HTTPException(502, "PayPal did not return an approval URL.")

        # Save a PENDING payment; stash PayPal order_id in reference_no
        payment = Payment(
            tenant_id      = PydanticObjectId(data.tenant_id),
            lease_id       = PydanticObjectId(data.lease_id),
            room_id        = PydanticObjectId(data.room_id),
            amount         = data.amount,
            method         = PaymentMethod.OTHER,   # "PAYPAL" — add to enum if desired
            type           = data.type,
            status         = PaymentStatus.PENDING,
            reference_no   = order_id,              # PayPal order ID stored here
            notes          = data.notes,
            period_start   = data.period_start,
            period_end     = data.period_end,
            recorded_by    = PydanticObjectId(recorded_by) if recorded_by else None,
            receipt_number = receipt_number,
        )
        saved = await payment_repository.save_payment(payment)

        return PayPalInitResponse(
            payment_id     = str(saved.id),
            receipt_number = receipt_number,
            order_id       = order_id,
            approval_url   = approval_url,
            amount         = data.amount,
            currency       = paypal_cfg.currency,
        )

    # ─────────────────────────────────────────────────────────────
    #  NEW — PayPal: capture (after tenant approves)
    # ─────────────────────────────────────────────────────────────

    async def capture_paypal_payment(
        self, data: PayPalCaptureRequest, recorded_by: str
    ) -> PaymentResponse:
        # 1. Load and validate internal payment
        payment = await self.get_payment_by_id(data.payment_id)
        if payment.status != PaymentStatus.PENDING:
            raise HTTPException(400, "Payment is not in PENDING status.")
        if payment.reference_no != data.order_id:
            raise HTTPException(400, "order_id does not match this payment record.")

        # 2. Call PayPal capture
        headers = await _paypal_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{paypal_cfg.base_url}/v2/checkout/orders/{data.order_id}/capture",
                headers=headers,
                json={},
            )

        if resp.status_code not in (200, 201):
            # Mark FAILED so it's not left dangling as PENDING
            payment.status     = PaymentStatus.FAILED
            payment.updated_at = datetime.utcnow()
            await payment_repository.save_payment(payment)
            raise HTTPException(502, f"PayPal capture failed: {resp.text}")

        capture_data    = resp.json()
        capture_unit    = capture_data["purchase_units"][0]["payments"]["captures"][0]
        capture_id      = capture_unit["id"]
        captured_amount = float(capture_unit["amount"]["value"])
        payer           = capture_data.get("payer", {})

        # 3. Confirm payment — reuse existing confirm logic pattern
        payment.status       = PaymentStatus.CONFIRMED
        payment.confirmed_at = datetime.utcnow()
        payment.updated_at   = datetime.utcnow()
        # Store capture details in receipt_url field (no schema change needed)
        # If you prefer a dedicated field, add paypal_capture_id to the model.
        payment.receipt_url  = capture_id                            # capture_id for refunds
        # Attach transient attrs for the response DTO
        payment.paypal_order_id    = data.order_id                  # type: ignore[attr-defined]
        payment.paypal_capture_id  = capture_id                     # type: ignore[attr-defined]
        payment.paypal_payer_id    = payer.get("payer_id")          # type: ignore[attr-defined]
        payment.paypal_payer_email = payer.get("email_address")     # type: ignore[attr-defined]

        saved = await payment_repository.save_payment(payment)

        # 4. Apply lease balance change — PayPal capture is the
        #    PENDING → CONFIRMED transition for an online payment.
        await self._apply_balance_change(
            lease_id = str(payment.lease_id),
            amount   = float(captured_amount or payment.amount or 0.0),
            action   = "settle",
        )

        # 5. Notify tenant
        await self._notify_tenant(
            lease_id     = str(payment.lease_id),
            title        = "Payment confirmed",
            message      = f"Your PayPal payment of ₱{captured_amount:,.2f} has been confirmed. Receipt: {payment.receipt_number}",
            reference_id = str(saved.id),
        )

        return PaymentResponse.from_payment(saved)

    # ─────────────────────────────────────────────────────────────
    #  NEW — PayPal: capture by order_id only (idempotent)
    # ─────────────────────────────────────────────────────────────

    async def capture_paypal_payment_by_token(
        self, order_id: str, recorded_by: str
    ) -> PaymentResponse:
        """
        Look up the internal Payment by its stored order_id (saved as
        ``reference_no`` during initiate) and capture it.

        Idempotent: if the payment is already CONFIRMED, returns it
        without calling PayPal again. This is the endpoint used by the
        PayPal return URL handler in the frontend, so a refresh or
        double-click doesn't blow up.
        """
        if not order_id:
            raise HTTPException(400, "PayPal order id (token) is required.")

        # Locate the matching internal payment
        payment = await Payment.find_one(Payment.reference_no == order_id)
        if not payment:
            raise HTTPException(
                404,
                "No matching payment found for this PayPal order. "
                "Please contact your manager.",
            )

        # Already captured? Just return it.
        if payment.status == PaymentStatus.CONFIRMED:
            return PaymentResponse.from_payment(payment)

        # Build the same DTO and reuse the existing capture path
        capture_dto = PayPalCaptureRequest(
            order_id   = order_id,
            payment_id = str(payment.id),
        )
        return await self.capture_paypal_payment(
            data        = capture_dto,
            recorded_by = recorded_by,
        )


# Singleton — matches your existing pattern
payment_service = PaymentService()