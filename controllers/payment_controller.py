from fastapi import APIRouter, Depends, HTTPException
from beanie import PydanticObjectId
from repository import tenant_repository

from config.jwt_middleware import get_current_user, require_roles
from services.payment_service import payment_service
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
from dto.response.api_response import ApiResponse

router = APIRouter(prefix="/api/payments", tags=["Payments"])


# ═══════════════════════════════════════════════════════════════
#  STATIC ROUTES FIRST (rule #9 — before /{id})
# ═══════════════════════════════════════════════════════════════

@router.get(
    "/stats",
    response_model=ApiResponse[PaymentStatsResponse],
    summary="Payment statistics",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER", "ROLE_STAFF"]))],
)
async def get_stats():
    result = await payment_service.get_payment_stats()
    return ApiResponse(is_success=True, message="Payment stats retrieved.", data=result)


@router.get(
    "/",
    response_model=ApiResponse[PaymentListResponse],
    summary="Get all payments",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER", "ROLE_STAFF"]))],
)
async def get_all_payments():
    payments = await payment_service.get_all_payments()
    return ApiResponse(
        is_success=True,
        message="Payments retrieved.",
        data=PaymentListResponse(
            total=len(payments),
            payments=[PaymentResponse.from_payment(p) for p in payments],
        ),
    )


@router.get(
    "/tenant/{tenant_id}",
    response_model=ApiResponse[PaymentListResponse],
    summary="Get payments for a tenant",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER", "ROLE_STAFF"]))],
)
async def get_tenant_payments(tenant_id: str):
    payments = await payment_service.get_tenant_payments(tenant_id)
    return ApiResponse(
        is_success=True,
        message="Tenant payments retrieved.",
        data=PaymentListResponse(
            total=len(payments),
            payments=[PaymentResponse.from_payment(p) for p in payments],
        ),
    )


@router.get(
    "/lease/{lease_id}",
    response_model=ApiResponse[PaymentListResponse],
    summary="Get payments for a lease",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER", "ROLE_STAFF"]))],
)
async def get_lease_payments(lease_id: str):
    payments = await payment_service.get_lease_payments(lease_id)
    return ApiResponse(
        is_success=True,
        message="Lease payments retrieved.",
        data=PaymentListResponse(
            total=len(payments),
            payments=[PaymentResponse.from_payment(p) for p in payments],
        ),
    )


# ─── PayPal ───────────────────────────────────────────────────────────────────

@router.post(
    "/paypal/initiate",
    response_model=ApiResponse[PayPalInitResponse],
    summary="Initiate a PayPal payment",
    description=(
        "Creates a PayPal order and returns the `approval_url`. "
        "Redirect the tenant to `approval_url` to complete payment on PayPal. "
        "After approval, call POST /paypal/capture."
    ),
)
async def initiate_paypal_payment(
    body: PayPalPaymentRequest,
    current_user: dict = Depends(get_current_user),
):
    result = await payment_service.initiate_paypal_payment(
        data        = body,
        recorded_by = str(current_user.id),
    )
    return ApiResponse(
        is_success=True,
        message="PayPal order created. Redirect tenant to approval_url.",
        data=result,
    )


@router.post(
    "/paypal/capture",
    response_model=ApiResponse[PaymentResponse],
    summary="Capture PayPal payment after tenant approval",
    description=(
        "Call this once the tenant has approved the payment on PayPal. "
        "Captures the order and marks the payment CONFIRMED."
    ),
)
async def capture_paypal_payment(
    body: PayPalCaptureRequest,
    current_user: dict = Depends(get_current_user),
):
    result = await payment_service.capture_paypal_payment(
        data        = body,
        recorded_by = str(current_user.id),
    )
    return ApiResponse(
        is_success=True,
        message="Payment captured and confirmed.",
        data=result,
    )


@router.post(
    "/paypal/capture-by-token",
    response_model=ApiResponse[PaymentResponse],
    summary="Capture a PayPal payment using only the PayPal order/token id",
    description=(
        "Convenience endpoint used by the frontend's PayPal return handler. "
        "Looks up the internal PENDING payment by its stored order_id, then "
        "captures and confirms it. Idempotent — if the payment is already "
        "CONFIRMED, the existing record is returned."
    ),
)
async def capture_paypal_payment_by_token(
    token: str,
    current_user: dict = Depends(get_current_user),
):
    result = await payment_service.capture_paypal_payment_by_token(
        order_id    = token,
        recorded_by = str(current_user.id),
    )
    return ApiResponse(
        is_success=True,
        message="Payment captured and confirmed.",
        data=result,
    )


# ─── Cash / Manual ────────────────────────────────────────────────────────────

@router.post(
    "/cash",
    response_model=ApiResponse[PaymentResponse],
    summary="Record a manual / cash payment",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER", "ROLE_STAFF"]))],
)
async def record_cash_payment(
    body: CashPaymentRequest,
    current_user: dict = Depends(get_current_user),
):
    result = await payment_service.record_cash_payment(
        data        = body,
        recorded_by = str(current_user.id),
    )
    return ApiResponse(is_success=True, message="Cash payment recorded.", data=result)


# ─── Confirm ──────────────────────────────────────────────────────────────────

@router.patch(
    "/{payment_id}/confirm",
    response_model=ApiResponse[PaymentResponse],
    summary="Confirm a pending payment",
    dependencies=[Depends(require_roles(["ROLE_ADMIN", "ROLE_MANAGER"]))],
)
async def confirm_payment(payment_id: str):
    payment = await payment_service.confirm_payment(payment_id)
    return ApiResponse(
        is_success=True,
        message="Payment confirmed.",
        data=PaymentResponse.from_payment(payment),
    )


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete(
    "/{payment_id}",
    response_model=ApiResponse[dict],
    summary="Delete a non-confirmed payment",
    dependencies=[Depends(require_roles(["ROLE_ADMIN"]))],
)
async def delete_payment(payment_id: str):
    result = await payment_service.delete_payment(payment_id)
    return ApiResponse(is_success=True, message=result["message"], data=result)


# ─── Self-service: tenant views their own payments ────────────────────────────

@router.get(
    "/me",
    response_model=ApiResponse[PaymentListResponse],
    summary="Get my payments (tenant self-service)",
)
async def get_my_payments(
    current_user=Depends(get_current_user),
):
    tenant = await tenant_repository.get_tenant_by_user_id(
        PydanticObjectId(str(current_user.id))
    )
    if not tenant:
        return ApiResponse.success(
            data=PaymentListResponse(total=0, payments=[]),
            message="No tenant profile found.",
        )
    payments = await payment_service.get_tenant_payments(str(tenant.id))
    return ApiResponse.success(
        data=PaymentListResponse(
            total=len(payments),
            payments=[PaymentResponse.from_payment(p) for p in payments],
        ),
        message="Your payments retrieved.",
    )


# ─── Single get (dynamic — always last) ───────────────────────────────────────

@router.get(
    "/{payment_id}",
    response_model=ApiResponse[PaymentResponse],
    summary="Get a single payment by ID",
)
async def get_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
):
    payment = await payment_service.get_payment_by_id(payment_id)

    # Tenants may only see their own payments
    if current_user.get("role") == "ROLE_TENANT":
        if str(payment.tenant_id) != current_user.username:
            raise HTTPException(403, "Access denied.")

    return ApiResponse(
        is_success=True,
        message="Payment retrieved.",
        data=PaymentResponse.from_payment(payment),
    )
