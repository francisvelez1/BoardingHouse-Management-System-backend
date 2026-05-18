"""
controllers/manager_controller.py

All HTTP endpoints for manager-facing operations.
Requires ROLE_MANAGER or ROLE_ADMIN.

NOTE: This controller uses your groupmates' existing function-based
services — no singleton instances needed.

Routes:
  /api/manager/rooms/**
  /api/manager/leases/**
  /api/manager/payments/**
  /api/manager/maintenance/**
  /api/manager/dashboard
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from beanie import PydanticObjectId
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from models.user import User, RoleName
from models.room import Room, RoomStatus, RoomType
from models.lease import Lease, LeaseStatus
from models.maintenance import MaintenanceStatus
from models.payment import Payment, PaymentStatus
from models.tenant import Tenant
from models.message import Message, MessageDirection, MessageStatus
from models.booking_request import BookingRequest, BookingStatus
from config.jwt_middleware import get_current_user

# ── Import your groupmates' existing services (function-based) ────────────────
from services import room_service
from services import lease_service
# FIX: payment_service is class-based — import the singleton instance, not the module
from services.payment_service import payment_service
# maintenance_service is class-based — import the singleton instance, not the module
from services.maintenance_service import maintenance_service
from services.communication_service import communication_service

# ── Import your groupmates' existing DTOs ────────────────────────────────────
from dto.request.room_request       import RoomCreateRequest, RoomUpdateRequest
from dto.request.lease_request      import LeaseCreateRequest, LeaseUpdateRequest, LeaseRenewRequest, LeaseTerminateRequest
from dto.request.manager_requests   import (
    RecordPaymentRequest,
    SubmitMaintenanceRequest,
    AssignMaintenanceRequest,
    CompleteMaintenanceRequest,
    RejectMaintenanceRequest,
    UpdateRoomStatusRequest,
)
from dto.response.manager_responses import (
    PaymentResponse, MaintenanceResponse,
    ManagerDashboardResponse,
    to_payment_response, to_maintenance_response,
)
from dto.response.tenant_response import TenantResponse

router = APIRouter(prefix="/api/manager", tags=["manager"])


# ── Auth dependency ───────────────────────────────────────────────────────────

async def require_manager(current_user: User = Depends(get_current_user)):
    """Requires ROLE_MANAGER or ROLE_ADMIN."""
    if current_user.role not in [RoleName.MANAGER, RoleName.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin access required.",
        )
    return current_user


# ── Ownership scoping helper ──────────────────────────────────────────────────
#
# All downstream entities (Lease, Payment, Maintenance, BookingRequest,
# Tenant.room_id) reference a Room by its *string* ObjectId. To scope these
# entities to "the manager's own data" we first resolve the manager's owned
# room-ids and then keep only items whose `room_id` is in that set.
#
# This is a post-fetch filter applied at the controller level — services and
# repositories remain global so they're still usable by admin endpoints, the
# tenant API, etc. The trade-off is fuzzy pagination at the boundary, which
# is acceptable for the small-to-medium scale of a boarding-house deployment.

async def _manager_room_id_set(manager_id) -> set[str]:
    """Returns the set of room-id strings owned by the given manager."""
    ids = await room_service.get_room_ids_for_manager(manager_id)
    return set(ids)


def _filter_by_room(items, owned_room_ids: set[str], attr: str = "room_id"):
    """
    Returns only those items whose `attr` (default 'room_id') value, when
    coerced to str, is in the owned-room set. Items with no `room_id`
    (e.g. legacy / orphaned records) are dropped — they cannot be safely
    attributed to a specific manager.
    """
    out = []
    for it in items:
        rid = getattr(it, attr, None)
        if rid is None and isinstance(it, dict):
            rid = it.get(attr)
        if rid is None:
            continue
        if str(rid) in owned_room_ids:
            out.append(it)
    return out


# ============================================================================
# DASHBOARD
# ============================================================================

@router.get("/dashboard", summary="Manager dashboard stats")
async def get_manager_dashboard(current_user: User = Depends(require_manager)):
    """
    Combined stats — occupancy + leases + maintenance, scoped to the
    rooms this manager owns. Cards on the dashboard therefore reflect
    only "my boarding house".
    """
    import logging
    logger = logging.getLogger(__name__)

    owned = await _manager_room_id_set(current_user.id)

    try:
        room_stats = await room_service.get_room_stats(manager_id=current_user.id)
    except Exception as exc:
        logger.error("room_service.get_room_stats() failed: %s", exc, exc_info=True)
        room_stats = {"total": 0, "vacant": 0, "occupied": 0, "occupancy_rate_pct": 0}

    try:
        # Lease counts are derived from leases attached to my rooms.
        all_leases    = await lease_service.get_all_leases(skip=0, limit=10_000)
        my_leases     = _filter_by_room(all_leases, owned)
        active_leases = [
            l for l in my_leases
            if getattr(l, "status", None) in (LeaseStatus.ACTIVE, "ACTIVE")
        ]
        lease_stats = {"total": len(my_leases), "active": len(active_leases)}
    except Exception as exc:
        logger.error("scoped lease stats failed: %s", exc, exc_info=True)
        lease_stats = {"total": 0, "active": 0}

    try:
        # Maintenance counts are derived from work-orders on my rooms.
        all_maint = await maintenance_service.get_all_requests()
        my_maint  = _filter_by_room(all_maint, owned)
        submitted_count   = sum(
            1 for r in my_maint
            if getattr(r, "status", None) in (MaintenanceStatus.SUBMITTED, "SUBMITTED")
        )
        in_progress_count = sum(
            1 for r in my_maint
            if getattr(r, "status", None) in (MaintenanceStatus.IN_PROGRESS, "IN_PROGRESS")
        )
        maintenance_stats = {
            "submitted":   submitted_count,
            "in_progress": in_progress_count,
        }
    except Exception as exc:
        logger.error("scoped maintenance stats failed: %s", exc, exc_info=True)
        maintenance_stats = {"submitted": 0, "in_progress": 0}

    return {
        "rooms":       room_stats,
        "leases":      lease_stats,
        "maintenance": maintenance_stats,
    }


# ============================================================================
# ROOM ENDPOINTS — uses your groupmate's room_service functions
# ============================================================================

@router.get("/rooms", summary="List all rooms")
async def list_rooms(
    status: Optional[RoomStatus] = Query(default=None),
    skip:   int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    # Scoped to "rooms I created". See models/room.py::manager_id and
    # repository/room_repository.py::_owner_clause for the ownership rules
    # (including the legacy created_by fallback for pre-migration rooms).
    return await room_service.get_rooms_for_manager(
        manager_id=current_user.id, skip=skip, limit=limit, status=status,
    )


@router.get("/rooms/vacant", summary="List vacant rooms")
async def list_vacant_rooms(
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    return await room_service.get_vacant_rooms_for_manager(
        manager_id=current_user.id, skip=skip, limit=limit,
    )


@router.get("/rooms/stats", summary="Room occupancy stats")
async def get_room_stats(current_user: User = Depends(require_manager)):
    return await room_service.get_room_stats(manager_id=current_user.id)


@router.get("/rooms/maintenance", summary="Rooms under maintenance")
async def list_maintenance_rooms(
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    return await room_service.get_rooms_under_maintenance_for_manager(
        manager_id=current_user.id, skip=skip, limit=limit,
    )


@router.get("/rooms/search", summary="Search rooms")
async def search_rooms(
    q:     str = Query(..., min_length=1),
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    return await room_service.search_rooms_for_manager(
        manager_id=current_user.id, query=q, skip=skip, limit=limit,
    )


@router.get("/rooms/{room_id}", summary="Get room by ID")
async def get_room(room_id: str, current_user: User = Depends(require_manager)):
    # Verify ownership before returning, so Manager B can't peek at
    # Manager A's room by guessing the id.
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.get_room_by_id(PydanticObjectId(room_id))


@router.post("/rooms", status_code=201, summary="Create a new room")
async def create_room(
    body: RoomCreateRequest,
    current_user: User = Depends(require_manager),
):
    return await room_service.create_room(
        request    = body,
        created_by = str(current_user.id),
        manager_id = current_user.id,
    )


@router.patch("/rooms/{room_id}", summary="Update room details")
async def update_room(
    room_id: str,
    body: RoomUpdateRequest,
    current_user: User = Depends(require_manager),
):
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.update_room(
        room_id    = PydanticObjectId(room_id),
        request    = body,
        updated_by = str(current_user.id),
    )


@router.patch("/rooms/{room_id}/status", summary="Update room status")
async def update_room_status(
    room_id: str,
    body: UpdateRoomStatusRequest,
    current_user: User = Depends(require_manager),
):
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.update_room_status(
        room_id    = PydanticObjectId(room_id),
        status     = body.status,
        updated_by = str(current_user.id),
    )


@router.patch("/rooms/{room_id}/maintenance/start", summary="Set room under maintenance")
async def start_room_maintenance(
    room_id: str,
    notes: str = Query(..., min_length=1),
    current_user: User = Depends(require_manager),
):
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.set_room_under_maintenance(
        room_id            = PydanticObjectId(room_id),
        maintenance_notes  = notes,
        updated_by         = str(current_user.id),
    )


@router.patch("/rooms/{room_id}/maintenance/complete", summary="Complete room maintenance")
async def complete_room_maintenance(
    room_id: str,
    current_user: User = Depends(require_manager),
):
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.complete_room_maintenance(
        room_id    = PydanticObjectId(room_id),
        updated_by = str(current_user.id),
    )


@router.delete("/rooms/{room_id}", summary="Delete a room")
async def delete_room(room_id: str, current_user: User = Depends(require_manager)):
    await room_service._assert_owns_room(
        PydanticObjectId(room_id), manager_id=current_user.id,
    )
    return await room_service.delete_room(PydanticObjectId(room_id))


# ============================================================================
# LEASE ENDPOINTS — uses your groupmate's lease_service functions
# ============================================================================

@router.get("/leases", summary="List all leases")
async def list_leases(
    status: Optional[LeaseStatus] = Query(default=None),
    skip:   int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    owned = await _manager_room_id_set(current_user.id)
    if status:
        leases = await lease_service.get_leases_by_status(status, skip=0, limit=10_000)
    else:
        leases = await lease_service.get_all_leases(skip=0, limit=10_000)
    scoped = _filter_by_room(leases, owned)
    # Apply pagination after scoping.
    return scoped[skip : skip + limit]


@router.get("/leases/stats", summary="Lease statistics")
async def get_lease_stats(current_user: User = Depends(require_manager)):
    owned  = await _manager_room_id_set(current_user.id)
    leases = await lease_service.get_all_leases(skip=0, limit=10_000)
    mine   = _filter_by_room(leases, owned)
    active = [l for l in mine if getattr(l, "status", None) in (LeaseStatus.ACTIVE, "ACTIVE")]
    return {"total": len(mine), "active": len(active)}


@router.get("/leases/expiring", summary="Leases expiring soon")
async def get_expiring_leases(
    days:  int = Query(default=30, ge=1),
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    owned  = await _manager_room_id_set(current_user.id)
    leases = await lease_service.get_expiring_leases(days_ahead=days, skip=0, limit=10_000)
    scoped = _filter_by_room(leases, owned)
    return scoped[skip : skip + limit]


@router.get("/leases/tenant/{tenant_id}", summary="Get leases by tenant")
async def get_tenant_leases(
    tenant_id: str,
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    owned  = await _manager_room_id_set(current_user.id)
    leases = await lease_service.get_leases_by_tenant(tenant_id, skip=0, limit=10_000)
    scoped = _filter_by_room(leases, owned)
    return scoped[skip : skip + limit]


@router.get("/leases/tenant/{tenant_id}/active", summary="Get active lease for tenant")
async def get_active_tenant_lease(
    tenant_id: str,
    current_user: User = Depends(require_manager),
):
    lease = await lease_service.get_active_lease_by_tenant(tenant_id)
    if lease is None:
        return None
    owned = await _manager_room_id_set(current_user.id)
    rid = getattr(lease, "room_id", None)
    if rid is None or str(rid) not in owned:
        # Don't leak a lease that belongs to another manager's room.
        return None
    return lease


@router.get("/leases/room/{room_id}", summary="Get leases by room")
async def get_room_leases(
    room_id: str,
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_manager),
):
    owned = await _manager_room_id_set(current_user.id)
    if room_id not in owned:
        raise HTTPException(403, "You can only view leases for rooms you own.")
    return await lease_service.get_leases_by_room(room_id, skip=skip, limit=limit)


@router.get("/leases/{lease_id}", summary="Get lease by ID")
async def get_lease(lease_id: str, current_user: User = Depends(require_manager)):
    lease = await lease_service.get_lease_by_id(PydanticObjectId(lease_id))
    owned = await _manager_room_id_set(current_user.id)
    rid = getattr(lease, "room_id", None)
    if rid is None or str(rid) not in owned:
        raise HTTPException(403, "You can only view leases for rooms you own.")
    return lease


@router.post("/leases", status_code=201, summary="Create a new lease")
async def create_lease(
    body: LeaseCreateRequest,
    current_user: User = Depends(require_manager),
):
    return await lease_service.create_lease(
        request    = body,
        created_by = str(current_user.id),
    )


@router.patch("/leases/{lease_id}", summary="Update lease details")
async def update_lease(
    lease_id: str,
    body: LeaseUpdateRequest,
    current_user: User = Depends(require_manager),
):
    return await lease_service.update_lease(
        lease_id   = PydanticObjectId(lease_id),
        request    = body,
        updated_by = str(current_user.id),
    )


@router.patch("/leases/{lease_id}/activate", summary="Activate a pending lease")
async def activate_lease(
    lease_id: str,
    current_user: User = Depends(require_manager),
):
    return await lease_service.activate_lease(
        lease_id   = PydanticObjectId(lease_id),
        updated_by = str(current_user.id),
    )


@router.patch("/leases/{lease_id}/renew", summary="Renew a lease")
async def renew_lease(
    lease_id: str,
    body: LeaseRenewRequest,
    current_user: User = Depends(require_manager),
):
    return await lease_service.renew_lease(
        lease_id   = PydanticObjectId(lease_id),
        request    = body,
        updated_by = str(current_user.id),
    )


@router.patch("/leases/{lease_id}/terminate", summary="Terminate a lease")
async def terminate_lease(
    lease_id: str,
    body: LeaseTerminateRequest,
    current_user: User = Depends(require_manager),
):
    return await lease_service.terminate_lease(
        lease_id   = PydanticObjectId(lease_id),
        request    = body,
        updated_by = str(current_user.id),
    )


@router.patch("/leases/{lease_id}/deposit/return", summary="Return security deposit")
async def return_deposit(
    lease_id:   str,
    deductions: float = Query(default=0.0, ge=0),
    current_user: User = Depends(require_manager),
):
    return await lease_service.return_deposit(
        lease_id   = PydanticObjectId(lease_id),
        deductions = deductions,
        updated_by = str(current_user.id),
    )


@router.delete("/leases/{lease_id}", summary="Delete a lease")
async def delete_lease(lease_id: str, _: User = Depends(require_manager)):
    return await lease_service.delete_lease(PydanticObjectId(lease_id))


# ============================================================================
# PAYMENT ENDPOINTS — uses payment_service singleton
# ============================================================================

@router.get("/payments", response_model=list[PaymentResponse], summary="List all payments")
async def list_payments(current_user: User = Depends(require_manager)):
    owned    = await _manager_room_id_set(current_user.id)
    payments = await payment_service.get_all_payments()
    mine     = _filter_by_room(payments, owned)
    return [to_payment_response(p) for p in mine]


@router.get("/payments/stats", summary="Payment statistics")
async def get_payment_stats(current_user: User = Depends(require_manager)):
    """
    Scoped payment statistics: only payments attached to rooms this
    manager owns are aggregated.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        owned    = await _manager_room_id_set(current_user.id)
        payments = await payment_service.get_all_payments()
        mine     = _filter_by_room(payments, owned)

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)

        paid_count    = sum(1 for p in mine if p.status == PaymentStatus.CONFIRMED)
        partial_count = sum(1 for p in mine if getattr(p.status, "value", p.status) == "PARTIAL")

        total_collected = sum(
            (p.amount or 0.0) for p in mine
            if p.status == PaymentStatus.CONFIRMED
        )
        monthly_collected = sum(
            (p.amount or 0.0) for p in mine
            if p.status == PaymentStatus.CONFIRMED
            and p.confirmed_at and p.confirmed_at >= month_start
        )

        # Outstanding and unpaid_count must both come from the lease's
        # running `outstanding_balance` rather than from PENDING payment
        # rows directly. The Payment service's `_apply_balance_change`
        # keeps that field perfectly in sync — charges bump it up,
        # confirmed payments bring it down. A PENDING row may still
        # exist in the table *after* the lease has been fully settled
        # (e.g. manager assigned a charge then recorded a separate cash
        # receipt with `+ Record Payment`, which creates a new
        # CONFIRMED row instead of mutating the original PENDING one);
        # counting those stale rows is what kept the "1 unpaid" and the
        # ₱X Outstanding number lingering on a lease that's actually
        # paid in full. We therefore:
        #   1. Use `lease.outstanding_balance` for the Outstanding total.
        #   2. For `unpaid_count`, only count PENDING payment rows whose
        #      lease still has a positive outstanding balance — stale
        #      PENDING rows on already-settled leases drop out.
        leases = await lease_service.get_all_leases(skip=0, limit=10_000)
        my_leases = [l for l in leases if getattr(l, "room_id", None) and str(l.room_id) in owned]
        total_outstanding = sum(
            max(0.0, (getattr(l, "outstanding_balance", 0.0) or 0.0)) for l in my_leases
        )
        leases_with_balance = {
            str(l.id)
            for l in my_leases
            if (getattr(l, "outstanding_balance", 0.0) or 0.0) > 0.0
        }
        unpaid_count = sum(
            1 for p in mine
            if p.status == PaymentStatus.PENDING
            and str(getattr(p, "lease_id", "")) in leases_with_balance
        )

        return {
            "paid_count":        paid_count,
            "unpaid_count":      unpaid_count,
            "partial_count":     partial_count,
            "total_collected":   round(total_collected,   2),
            "monthly_collected": round(monthly_collected, 2),
            "monthly_revenue":   round(monthly_collected, 2),
            "total_outstanding": round(total_outstanding, 2),
        }
    except Exception as exc:
        logger.error("scoped payment stats failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment stats unavailable: {exc}",
        )


@router.get("/payments/tenant/{tenant_id}", response_model=list[PaymentResponse])
async def get_tenant_payments(tenant_id: str, current_user: User = Depends(require_manager)):
    owned    = await _manager_room_id_set(current_user.id)
    payments = await payment_service.get_tenant_payments(tenant_id)
    mine     = _filter_by_room(payments, owned)
    return [to_payment_response(p) for p in mine]


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, current_user: User = Depends(require_manager)):
    payment = await payment_service.get_payment_by_id(payment_id)
    owned   = await _manager_room_id_set(current_user.id)
    if getattr(payment, "room_id", None) is None or str(payment.room_id) not in owned:
        raise HTTPException(403, "You can only view payments for rooms you own.")
    return to_payment_response(payment)


@router.post("/payments", response_model=PaymentResponse, status_code=201)
async def record_payment(
    body: RecordPaymentRequest,
    current_user: User = Depends(require_manager),
):
    payment = await payment_service.record_payment(
        tenant_id    = body.tenant_id,
        lease_id     = body.lease_id,
        room_id      = body.room_id,
        amount       = body.amount,
        method       = body.method,
        type         = body.type,
        reference_no = body.reference_no,
        notes        = body.notes,
        period_start = body.period_start,
        period_end   = body.period_end,
        recorded_by  = str(current_user.id),
        # Body may override default (CONFIRMED). PENDING is used by the
        # "Assign Payment" flow from the Leases tab to create a charge
        # that the tenant has to pay later.
        status       = body.status or PaymentStatus.CONFIRMED,
    )
    return to_payment_response(payment)


@router.patch("/payments/{payment_id}/confirm", response_model=PaymentResponse)
async def confirm_payment(payment_id: str, _: User = Depends(require_manager)):
    payment = await payment_service.confirm_payment(payment_id)
    return to_payment_response(payment)


@router.delete("/payments/{payment_id}")
async def delete_payment(payment_id: str, _: User = Depends(require_manager)):
    return await payment_service.delete_payment(payment_id)


# ============================================================================
# MAINTENANCE ENDPOINTS — uses maintenance_service
# ============================================================================

@router.get("/maintenance", response_model=list[MaintenanceResponse])
async def list_maintenance(
    status: Optional[MaintenanceStatus] = Query(default=None),
    current_user: User = Depends(require_manager),
):
    owned = await _manager_room_id_set(current_user.id)
    if status:
        reqs = await maintenance_service.get_requests_by_status(status)
    else:
        reqs = await maintenance_service.get_all_requests()
    mine = _filter_by_room(reqs, owned)
    return [to_maintenance_response(r) for r in mine]


@router.get("/maintenance/pending", response_model=list[MaintenanceResponse])
async def get_pending_maintenance(current_user: User = Depends(require_manager)):
    owned = await _manager_room_id_set(current_user.id)
    reqs  = await maintenance_service.get_pending_requests()
    mine  = _filter_by_room(reqs, owned)
    return [to_maintenance_response(r) for r in mine]


@router.get("/maintenance/stats")
async def get_maintenance_stats(current_user: User = Depends(require_manager)):
    owned = await _manager_room_id_set(current_user.id)
    reqs  = await maintenance_service.get_all_requests()
    mine  = _filter_by_room(reqs, owned)
    submitted   = sum(1 for r in mine if getattr(r, "status", None) in (MaintenanceStatus.SUBMITTED, "SUBMITTED"))
    in_progress = sum(1 for r in mine if getattr(r, "status", None) in (MaintenanceStatus.IN_PROGRESS, "IN_PROGRESS"))
    completed   = sum(1 for r in mine if getattr(r, "status", None) in (MaintenanceStatus.COMPLETED, "COMPLETED"))
    return {
        "total":       len(mine),
        "submitted":   submitted,
        "in_progress": in_progress,
        "completed":   completed,
    }


@router.get("/maintenance/tenant/{tenant_id}", response_model=list[MaintenanceResponse])
async def get_tenant_maintenance(tenant_id: str, current_user: User = Depends(require_manager)):
    owned = await _manager_room_id_set(current_user.id)
    reqs  = await maintenance_service.get_tenant_requests(tenant_id)
    mine  = _filter_by_room(reqs, owned)
    return [to_maintenance_response(r) for r in mine]


@router.get("/maintenance/{request_id}", response_model=MaintenanceResponse)
async def get_maintenance_request(request_id: str, current_user: User = Depends(require_manager)):
    req   = await maintenance_service.get_request_by_id(request_id)
    owned = await _manager_room_id_set(current_user.id)
    if getattr(req, "room_id", None) is None or str(req.room_id) not in owned:
        raise HTTPException(403, "You can only view maintenance requests for rooms you own.")
    return to_maintenance_response(req)


@router.post("/maintenance", response_model=MaintenanceResponse, status_code=201)
async def submit_maintenance(
    body: SubmitMaintenanceRequest,
    _: User = Depends(require_manager),
):
    req = await maintenance_service.submit_request(
        tenant_id   = body.tenant_id,
        room_id     = body.room_id,
        title       = body.title,
        description = body.description,
        category    = body.category,
        priority    = body.priority,
        photos      = body.photos,
    )
    return to_maintenance_response(req)


@router.patch("/maintenance/{request_id}/assign", response_model=MaintenanceResponse)
async def assign_maintenance(
    request_id: str,
    body: AssignMaintenanceRequest,
    _: User = Depends(require_manager),
):
    req = await maintenance_service.assign_request(request_id, body.assigned_to)
    return to_maintenance_response(req)


@router.patch("/maintenance/{request_id}/start", response_model=MaintenanceResponse)
async def start_maintenance(request_id: str, _: User = Depends(require_manager)):
    req = await maintenance_service.start_request(request_id)
    return to_maintenance_response(req)


@router.patch("/maintenance/{request_id}/complete", response_model=MaintenanceResponse)
async def complete_maintenance(
    request_id: str,
    body: CompleteMaintenanceRequest,
    _: User = Depends(require_manager),
):
    req = await maintenance_service.complete_request(request_id, body.resolution)
    return to_maintenance_response(req)


@router.patch("/maintenance/{request_id}/close", response_model=MaintenanceResponse)
async def close_maintenance(request_id: str, _: User = Depends(require_manager)):
    req = await maintenance_service.close_request(request_id)
    return to_maintenance_response(req)


@router.patch("/maintenance/{request_id}/reject", response_model=MaintenanceResponse)
async def reject_maintenance(
    request_id: str,
    body: RejectMaintenanceRequest,
    _: User = Depends(require_manager),
):
    req = await maintenance_service.reject_request(request_id, body.rejection_reason)
    return to_maintenance_response(req)


@router.delete("/maintenance/{request_id}")
async def delete_maintenance(request_id: str, _: User = Depends(require_manager)):
    return await maintenance_service.delete_request(request_id)


# ============================================================================
# TENANT UNASSIGN
# ============================================================================

@router.delete("/tenants/{tenant_id}/unassign", summary="Unassign a tenant from their room")
async def unassign_tenant(
    tenant_id: str,
    current_user: User = Depends(require_manager),
):
    """
    Manager-only operation. Marks the tenant INACTIVE, terminates the active
    lease, and frees up the room.
    """
    from models.tenant import TenantStatus
    tenant = await Tenant.get(PydanticObjectId(tenant_id))
    if not tenant:
        raise HTTPException(404, "Tenant not found.")

    # Terminate any active lease
    active_lease = await Lease.find_one({
        "tenant_id": str(tenant.id),
        "status": LeaseStatus.ACTIVE.value,
    })
    if active_lease:
        active_lease.status     = LeaseStatus.TERMINATED
        active_lease.updated_at = datetime.utcnow()
        await active_lease.save()

    # Free up the room
    if tenant.room_id:
        room = await Room.get(PydanticObjectId(tenant.room_id))
        if room:
            room.status            = RoomStatus.VACANT
            room.current_occupants = max(0, room.current_occupants - 1)
            room.updated_at        = datetime.utcnow()
            await room.save()

    tenant.room_id       = None
    tenant.status        = TenantStatus.INACTIVE
    tenant.move_out_date = datetime.utcnow()
    tenant.updated_at    = datetime.utcnow()
    await tenant.save()

    return {"message": "Tenant unassigned successfully.", "tenant_id": str(tenant.id)}


# ============================================================================
# MESSAGES (manager-side)
# ============================================================================

class _ManagerSendMessageBody(BaseModel):
    receiver_id: str
    tenant_id:   str
    body:        str = Field(..., min_length=1, max_length=2000)
    subject:     Optional[str] = Field(default=None, max_length=200)
    thread_id:   Optional[str] = None


def _msg_to_dict(m: Message, tenant_name: str = "") -> dict:
    return {
        "id":          str(m.id),
        "sender_id":   str(m.sender_id),
        "receiver_id": str(m.receiver_id),
        "tenant_id":   str(m.tenant_id),
        "tenant_name": tenant_name,
        "subject":     m.subject,
        "body":        m.body,
        "direction":   m.direction.value if hasattr(m.direction, "value") else m.direction,
        "status":      m.status.value if hasattr(m.status, "value") else m.status,
        "thread_id":   m.thread_id,
        "created_at":  m.created_at.isoformat() if m.created_at else None,
        "read_at":     m.read_at.isoformat() if m.read_at else None,
    }


@router.get("/messages", summary="List messages where the current manager is participant")
async def list_manager_messages(current_user: User = Depends(require_manager)):
    uid = PydanticObjectId(str(current_user.id))
    msgs = await Message.find(
        {"$or": [{"sender_id": uid}, {"receiver_id": uid}]}
    ).sort("-created_at").to_list()

    # Resolve tenant display names in batch
    tenant_ids = list({str(m.tenant_id) for m in msgs})
    tenant_map: dict[str, str] = {}
    for tid in tenant_ids:
        try:
            t = await Tenant.get(PydanticObjectId(tid))
            if t:
                tenant_map[tid] = t.full_name
        except Exception:
            continue

    return [_msg_to_dict(m, tenant_map.get(str(m.tenant_id), "Tenant")) for m in msgs]


@router.get("/messages/tenants", summary="List tenants the manager can message")
async def list_messageable_tenants(current_user: User = Depends(require_manager)):
    """Only tenants assigned to one of the manager's rooms can be messaged."""
    from models.tenant import TenantStatus
    owned   = await _manager_room_id_set(current_user.id)
    tenants = await Tenant.find(
        {"status": {"$in": [TenantStatus.ACTIVE.value, TenantStatus.PENDING.value]}}
    ).to_list()
    mine = [t for t in tenants if t.room_id and str(t.room_id) in owned]
    return [
        {
            "id":        str(t.id),
            "user_id":   t.user_id or "",
            "full_name": t.full_name,
            "email":     t.email,
            "phone":     t.phone,
            "room_id":   t.room_id,
        }
        for t in mine
    ]


@router.post("/messages/send", summary="Send a message from manager to a tenant", status_code=status.HTTP_201_CREATED)
async def manager_send_message(
    body: _ManagerSendMessageBody,
    current_user: User = Depends(require_manager),
):
    if not body.receiver_id:
        raise HTTPException(400, "receiver_id is required.")
    msg = await communication_service.send_message(
        sender_id   = str(current_user.id),
        receiver_id = body.receiver_id,
        tenant_id   = body.tenant_id,
        body        = body.body,
        direction   = MessageDirection.MANAGEMENT_TO_TENANT,
        subject     = body.subject,
        thread_id   = body.thread_id,
    )
    return _msg_to_dict(msg)


@router.get("/messages/thread/{thread_id}", summary="Get full message thread")
async def manager_get_thread(thread_id: str, _: User = Depends(require_manager)):
    messages = await communication_service.get_thread(thread_id)
    return [_msg_to_dict(m) for m in messages]


# ============================================================================
# SCOPED TENANTS  (only tenants in rooms this manager owns)
# ============================================================================
#
# The global /api/tenants endpoint is shared with admin tooling and remains
# unscoped. The manager dashboard uses these endpoints instead so it only
# ever sees its own tenants.

def _tenant_to_dict(t: Tenant) -> dict:
    """Mirror of tenant_response.from_tenant for the manager-scoped list."""
    return {
        "id":                  str(t.id),
        "user_id":             t.user_id or "",
        "first_name":          t.first_name,
        "last_name":           t.last_name,
        "full_name":           t.full_name,
        "email":               t.email,
        "phone":               t.phone,
        "id_type":             getattr(t.id_type, "value", t.id_type) if t.id_type else None,
        "id_number":           t.id_number,
        "id_verified":         t.id_verified,
        "emergency_contact":   t.emergency_contact.model_dump() if t.emergency_contact else None,
        "room_id":             t.room_id,
        "status":              getattr(t.status, "value", t.status),
        "move_in_date":        t.move_in_date.isoformat()  if t.move_in_date  else None,
        "move_out_date":       t.move_out_date.isoformat() if t.move_out_date else None,
        "deposit_paid":        t.deposit_paid,
        "advance_paid":        t.advance_paid,
        "outstanding_balance": t.outstanding_balance,
        "occupation":          t.occupation,
        "employer":            t.employer,
        "notes":               t.notes,
        "created_at":          t.created_at.isoformat() if t.created_at else None,
        "updated_at":          t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/tenants", summary="List tenants assigned to this manager's rooms")
async def list_manager_tenants(
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_manager),
):
    """
    Returns only tenants who are currently assigned to a room owned by
    the calling manager. Tenants with no `room_id` (unassigned) are
    intentionally excluded from this list — they are visible only to
    admins via the global /api/tenants endpoint.

    Important: we serialize through `TenantResponse.from_tenant` rather
    than returning raw `Tenant` documents. Beanie documents serialize
    Mongo's native `_id` field (not `id`) and *omit* `@property` fields
    like `full_name`. The Manager dashboard's tenant <select> dropdowns
    bind to `t.id` and `t.full_name` — so returning raw documents made
    every <option> render with no value and no visible label, which
    looked exactly like "no tenants in the dropdown" even when the
    manager owned tenants.
    """
    owned   = await _manager_room_id_set(current_user.id)
    tenants = await Tenant.find_all().to_list()
    mine = [t for t in tenants if t.room_id and str(t.room_id) in owned]
    return [TenantResponse.from_tenant(t) for t in mine[skip : skip + limit]]


@router.get("/tenants/stats", summary="Tenant statistics scoped to this manager")
async def get_manager_tenant_stats(current_user: User = Depends(require_manager)):
    from models.tenant import TenantStatus
    owned   = await _manager_room_id_set(current_user.id)
    tenants = await Tenant.find_all().to_list()
    mine    = [t for t in tenants if t.room_id and str(t.room_id) in owned]
    active  = sum(1 for t in mine if t.status in (TenantStatus.ACTIVE, "ACTIVE"))
    pending = sum(1 for t in mine if t.status in (TenantStatus.PENDING, "PENDING"))
    return {
        "total":   len(mine),
        "active":  active,
        "pending": pending,
    }


# ============================================================================
# SCOPED BOOKING REQUESTS  (only applications for rooms this manager owns)
# ============================================================================

# The actual fields on `BookingRequest` are `full_name`, `email`, `phone`,
# `desired_move_in_date`, `address`, etc. — *not* `applicant_name`,
# `applicant_email`, or `preferred_move_in_date`. Delegating to the
# canonical serializer in `booking_request_controller` keeps the
# manager-scoped endpoint in lock-step with the frontend's `BookingItem`
# type (see `services/bookingService.ts`). Without this, the booking
# cards on the manager dashboard rendered blank — which looked like
# "the pending request isn't reflecting".
from controllers.booking_request_controller import _booking_dict as _booking_to_dict  # noqa: E402


@router.get("/bookings", summary="List booking applications for this manager's rooms")
async def list_manager_bookings(
    status_filter: Optional[BookingStatus] = Query(default=None, alias="status"),
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_manager),
):
    """
    Returns booking applications whose `room_id` is one of the manager's
    own rooms. Used by the manager dashboard so two managers never see
    each other's pending applications.
    """
    owned = await _manager_room_id_set(current_user.id)

    query: dict = {}
    if status_filter:
        query["status"] = status_filter.value

    reqs = await BookingRequest.find(query).sort(-BookingRequest.created_at).to_list()
    mine = [b for b in reqs if b.room_id and str(b.room_id) in owned]
    paged = mine[skip : skip + limit]
    return {
        "total":    len(mine),
        "skip":     skip,
        "limit":    limit,
        "bookings": [_booking_to_dict(b) for b in paged],
    }


# ============================================================================
# ANALYTICS — used by the manager dashboard charts
# ============================================================================

@router.get("/analytics", summary="Aggregated analytics for the manager dashboard")
async def get_manager_analytics(current_user: User = Depends(require_manager)):
    """
    Returns the full analytics payload the dashboard charts expect,
    scoped to the rooms this manager owns:
    - monthly_revenue (last 6 calendar months: actual vs target)
    - collection_rate
    - top_rooms (highest earners)
    - outstanding_tenants
    - occupancy + occupancy_by_type
    - summary totals
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        owned = await _manager_room_id_set(current_user.id)

        # ── Monthly revenue (last 6 months, actual vs target) ─────────────
        now = datetime.utcnow()
        month_starts: list[datetime] = []
        for i in range(5, -1, -1):
            year  = now.year
            month = now.month - i
            while month <= 0:
                month += 12
                year  -= 1
            month_starts.append(datetime(year, month, 1))

        all_payments = await Payment.find_all().to_list()
        all_payments = _filter_by_room(all_payments, owned)
        confirmed    = [p for p in all_payments if p.status == PaymentStatus.CONFIRMED]

        active_leases = await Lease.find(Lease.status == LeaseStatus.ACTIVE).to_list()
        active_leases = _filter_by_room(active_leases, owned)
        target_revenue = sum((l.monthly_rate or 0.0) for l in active_leases)

        monthly_revenue = []
        for i, ms in enumerate(month_starts):
            next_ms = month_starts[i + 1] if i + 1 < len(month_starts) else (ms + timedelta(days=32)).replace(day=1)
            month_total = sum(
                (p.amount or 0.0)
                for p in confirmed
                if p.confirmed_at and ms <= p.confirmed_at < next_ms
            )
            monthly_revenue.append({
                "month":   ms.strftime("%b %Y"),
                "revenue": round(month_total, 2),
                "target":  round(target_revenue, 2),
            })

        # ── Collection rate ───────────────────────────────────────────────
        total_collected   = sum((p.amount or 0.0) for p in confirmed)
        total_outstanding = sum((l.outstanding_balance or 0.0) for l in active_leases)
        denom             = total_collected + total_outstanding
        collection_rate   = round((total_collected / denom) * 100.0, 1) if denom > 0 else 0.0

        # ── Top earning rooms ─────────────────────────────────────────────
        room_totals: dict[str, float] = {}
        for p in confirmed:
            rid = str(p.room_id)
            room_totals[rid] = room_totals.get(rid, 0.0) + (p.amount or 0.0)

        top_rooms = []
        for rid, total in sorted(room_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]:
            try:
                room = await Room.get(PydanticObjectId(rid))
                room_number = room.room_number if room else rid[:8]
            except Exception:
                room_number = rid[:8]
            top_rooms.append({
                "room_id":      rid,
                "room_number":  room_number,
                "total_earned": round(total, 2),
            })

        # ── Outstanding tenants ───────────────────────────────────────────
        outstanding_tenants = []
        for l in active_leases:
            if (l.outstanding_balance or 0.0) <= 0:
                continue
            try:
                tenant = await Tenant.get(PydanticObjectId(l.tenant_id))
            except Exception:
                tenant = None
            if not tenant:
                continue
            try:
                room = await Room.get(PydanticObjectId(l.room_id)) if l.room_id else None
            except Exception:
                room = None
            outstanding_tenants.append({
                "tenant_id":           str(tenant.id),
                "tenant_name":         tenant.full_name,
                "room_number":         room.room_number if room else "",
                "outstanding_balance": round(l.outstanding_balance or 0.0, 2),
                "monthly_rate":        round(l.monthly_rate or 0.0, 2),
            })
        outstanding_tenants.sort(key=lambda t: t["outstanding_balance"], reverse=True)
        outstanding_tenants = outstanding_tenants[:10]

        # ── Occupancy (scoped to this manager's rooms) ────────────────────
        from repository import room_repository
        all_rooms = await room_repository.get_rooms_by_manager(
            manager_id=current_user.id, skip=0, limit=10_000,
        )
        total_rooms    = len(all_rooms)
        occupied_rooms = sum(1 for r in all_rooms if r.status == RoomStatus.OCCUPIED)
        vacant_rooms   = sum(1 for r in all_rooms if r.status == RoomStatus.VACANT)
        rate_pct       = round((occupied_rooms / total_rooms) * 100.0, 1) if total_rooms > 0 else 0.0

        # By type
        occupancy_by_type = []
        for rt in RoomType:
            in_type = [r for r in all_rooms if r.room_type == rt]
            if not in_type:
                continue
            occ = sum(1 for r in in_type if r.status == RoomStatus.OCCUPIED)
            tot = len(in_type)
            occupancy_by_type.append({
                "type":     rt.value.title(),
                "occupied": occ,
                "total":    tot,
                "pct":      round((occ / tot) * 100.0, 1) if tot > 0 else 0.0,
            })

        return {
            "monthly_revenue":     monthly_revenue,
            "collection_rate":     collection_rate,
            "top_rooms":           top_rooms,
            "outstanding_tenants": outstanding_tenants,
            "occupancy": {
                "total":    total_rooms,
                "occupied": occupied_rooms,
                "vacant":   vacant_rooms,
                "rate_pct": rate_pct,
            },
            "occupancy_by_type":   occupancy_by_type,
            "summary": {
                "total_rooms":       total_rooms,
                "active_leases":     len(active_leases),
                "total_payments":    len(all_payments),
                "total_collected":   round(total_collected, 2),
                "total_outstanding": round(total_outstanding, 2),
            },
        }
    except Exception as exc:
        logger.error("get_manager_analytics failed: %s", exc, exc_info=True)
        # Return an empty-but-valid payload so the UI never breaks
        return {
            "monthly_revenue":     [],
            "collection_rate":     0.0,
            "top_rooms":           [],
            "outstanding_tenants": [],
            "occupancy": {"total": 0, "occupied": 0, "vacant": 0, "rate_pct": 0.0},
            "occupancy_by_type":   [],
            "summary": {
                "total_rooms":       0,
                "active_leases":     0,
                "total_payments":    0,
                "total_collected":   0.0,
                "total_outstanding": 0.0,
            },
        }