"""
controllers/booking_request_controller.py

Endpoints for:
- Tenants applying to book a room
- Managers / Admins reviewing / approving / rejecting bookings
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from beanie import PydanticObjectId
from typing import Optional
from datetime import datetime, date

from models.user import User, RoleName
from models.booking_request import BookingRequest, BookingStatus
from models.room import Room, RoomStatus
from models.tenant import Tenant, TenantStatus
from models.lease import Lease, LeaseStatus, PaymentFrequency
from models.manager_role_request import ManagerRoleRequest, ManagerRequestStatus
from config.jwt_middleware import get_current_user, require_roles

router = APIRouter(prefix="/api/bookings", tags=["Booking Requests"])


# ── Request / Response schemas ────────────────────────────────────────────

from pydantic import BaseModel


class BookingApplyRequest(BaseModel):
    room_id:              str
    full_name:            str
    email:                str
    phone:                str
    address:              str
    city:                 Optional[str] = None
    province:             Optional[str] = None
    desired_move_in_date: Optional[date] = None
    message:              Optional[str] = None
    id_document:          Optional[str] = None
    # Personal details
    last_name:        Optional[str]   = None
    date_of_birth:    Optional[date]  = None
    gender:           Optional[str]   = None
    civil_status:     Optional[str]   = None
    nationality:      Optional[str]   = "Filipino"
    occupation:       Optional[str]   = None
    employer:         Optional[str]   = None
    monthly_income:   Optional[float] = None
    # Emergency contact
    emergency_contact_name:         Optional[str] = None
    emergency_contact_phone:        Optional[str] = None
    emergency_contact_relationship: Optional[str] = None


class ReviewBookingRequest(BaseModel):
    status:       BookingStatus
    review_notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────

async def get_booking_or_404(booking_id: str) -> BookingRequest:
    b = await BookingRequest.get(PydanticObjectId(booking_id))
    if not b:
        raise HTTPException(404, "Booking request not found.")
    return b


async def get_room_or_404(room_id: str) -> Room:
    r = await Room.get(PydanticObjectId(room_id))
    if not r:
        raise HTTPException(404, "Room not found.")
    return r


# ============================================================================
# TENANT / PUBLIC ENDPOINTS
# ============================================================================

@router.post(
    "/apply",
    status_code=status.HTTP_201_CREATED,
    summary="Apply to book a room",
)
async def apply_booking(
    body: BookingApplyRequest,
    current_user: User = Depends(get_current_user),
):
    """Authenticated users may submit a booking application for a vacant room."""

    # Block if user has a rejected manager role request
    rejected_mgr = await ManagerRoleRequest.find_one({
        "user_id": str(current_user.id),
        "status": ManagerRequestStatus.REJECTED.value,
    })
    if rejected_mgr:
        raise HTTPException(
            403,
            "Your manager role application was rejected. "
            "You cannot book a room. Please contact the admin.",
        )

    room = await get_room_or_404(body.room_id)

    if not room.is_vacant:
        raise HTTPException(400, "This room is no longer available for booking.")

    # Prevent duplicate pending applications for same room by same user
    existing = await BookingRequest.find_one(
        {
            "user_id": str(current_user.id),
            "room_id": body.room_id,
            "status": BookingStatus.PENDING.value,
        }
    )
    if existing:
        raise HTTPException(
            400,
            "You already have a pending booking request for this room.",
        )

    req = BookingRequest(
        user_id              = str(current_user.id),
        room_id              = body.room_id,
        room_number          = room.room_number,
        monthly_rent         = room.monthly_rate,
        full_name            = body.full_name,
        email                = body.email,
        phone                = body.phone,
        address              = body.address,
        city                 = body.city,
        province             = body.province,
        desired_move_in_date = body.desired_move_in_date,
        message              = body.message,
        id_document          = body.id_document,
        last_name                       = body.last_name,
        date_of_birth                   = body.date_of_birth,
        gender                          = body.gender,
        civil_status                    = body.civil_status,
        nationality                     = body.nationality,
        occupation                      = body.occupation,
        employer                        = body.employer,
        monthly_income                  = body.monthly_income,
        emergency_contact_name          = body.emergency_contact_name,
        emergency_contact_phone         = body.emergency_contact_phone,
        emergency_contact_relationship  = body.emergency_contact_relationship,
    )
    await req.insert()

    # ── Notify all managers / admins so the request actually "arrives" ──
    try:
        from models.notification import (
            Notification, NotificationType, NotificationPriority,
        )
        recipients = await User.find(
            {"role": {"$in": [RoleName.MANAGER.value, RoleName.ADMIN.value]}}
        ).to_list()
        title   = f"New booking request for Room {room.room_number}"
        message = (
            f"{body.full_name} applied to book Room {room.room_number}. "
            f"Please review the application."
        )
        for mgr in recipients:
            try:
                await Notification(
                    recipient_id      = str(mgr.id),
                    sender_id         = str(current_user.id),
                    notification_type = NotificationType.ANNOUNCEMENT,
                    priority          = NotificationPriority.HIGH,
                    title             = title,
                    message           = message,
                    reference_id      = str(req.id),
                    reference_type    = "booking_request",
                ).insert()
            except Exception:
                # never block the application on notification errors
                continue
    except Exception:
        pass

    return {
        "message": "Booking request submitted successfully. Awaiting manager review.",
        "id": str(req.id),
    }


@router.get(
    "/my",
    summary="Get my booking requests",
)
async def get_my_bookings(
    current_user: User = Depends(get_current_user),
):
    """Returns all booking requests made by the current user."""
    reqs = await BookingRequest.find({"user_id": str(current_user.id)}).sort(-BookingRequest.created_at).to_list()
    return {
        "bookings": [
            {
                "id":                 str(r.id),
                "room_id":            r.room_id,
                "room_number":        r.room_number,
                "monthly_rent":       r.monthly_rent,
                "full_name":          r.full_name,
                "email":              r.email,
                "phone":              r.phone,
                "address":            r.address,
                "desired_move_in_date": r.desired_move_in_date.isoformat() if r.desired_move_in_date else None,
                "message":            r.message,
                "status":             r.status.value,
                "review_notes":       r.review_notes,
                "created_at":         r.created_at.isoformat(),
            }
            for r in reqs
        ]
    }


# ── Serializer ────────────────────────────────────────────────────────────

def _booking_dict(r: BookingRequest) -> dict:
    """Serialize a BookingRequest to a dict with all fields for the manager view."""
    return {
        "id":                 str(r.id),
        "user_id":            r.user_id,
        "room_id":            r.room_id,
        "room_number":        r.room_number,
        "monthly_rent":       r.monthly_rent,
        # Applicant basics
        "full_name":          r.full_name,
        "last_name":          r.last_name,
        "email":              r.email,
        "phone":              r.phone,
        # Address
        "address":            r.address,
        "city":               r.city,
        "province":           r.province,
        # Personal details
        "date_of_birth":      r.date_of_birth.isoformat() if r.date_of_birth else None,
        "gender":             r.gender,
        "civil_status":       r.civil_status,
        "nationality":        r.nationality,
        "occupation":         r.occupation,
        "employer":           r.employer,
        "monthly_income":     r.monthly_income,
        # Emergency contact
        "emergency_contact_name":         r.emergency_contact_name,
        "emergency_contact_phone":        r.emergency_contact_phone,
        "emergency_contact_relationship": r.emergency_contact_relationship,
        # Booking details
        "desired_move_in_date": r.desired_move_in_date.isoformat() if r.desired_move_in_date else None,
        "message":            r.message,
        "id_document":        r.id_document,
        # Review state
        "status":             r.status.value,
        "reviewed_by":        r.reviewed_by,
        "reviewed_at":        r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_notes":       r.review_notes,
        # Audit
        "created_at":         r.created_at.isoformat(),
        "updated_at":         r.updated_at.isoformat(),
    }


# ============================================================================
# MANAGER / ADMIN ENDPOINTS
# ============================================================================

@router.get(
    "/manager/all",
    summary="List all booking applications (manager / admin)",
)
async def list_all_bookings(
    status: Optional[BookingStatus] = Query(default=None),
    skip:   int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    """Manager / Admin view. Filter by PENDING, APPROVED, REJECTED, or CANCELLED."""
    query = {}
    if status:
        query["status"] = status.value

    reqs = await BookingRequest.find(query).sort(-BookingRequest.created_at).skip(skip).limit(limit).to_list()
    total = await BookingRequest.find(query).count()

    return {
        "total": total,
        "skip":  skip,
        "limit": limit,
        "bookings": [_booking_dict(r) for r in reqs],
    }


@router.get(
    "/manager/{booking_id}",
    summary="Get single booking detail (manager / admin)",
)
async def get_booking_detail(
    booking_id: str,
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    r = await get_booking_or_404(booking_id)
    return _booking_dict(r)


@router.patch(
    "/manager/{booking_id}/review",
    summary="Approve or reject a booking request",
)
async def review_booking(
    booking_id: str,
    body: ReviewBookingRequest,
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    """
    Manager/Admin reviews a booking.
    If APPROVED, the room is marked RESERVED (actual lease creation is separate).
    """
    req = await get_booking_or_404(booking_id)

    if req.status != BookingStatus.PENDING:
        raise HTTPException(400, "This booking has already been reviewed.")

    # If we're approving, the target room must still be vacant.
    # Otherwise we'd leave the booking in an "APPROVED but no tenant"
    # zombie state, which is what was producing the "Reserved" duplicate
    # rows in the Tenants tab.
    if body.status == BookingStatus.APPROVED:
        target_room = await Room.get(PydanticObjectId(req.room_id))
        if not target_room:
            raise HTTPException(404, "Room not found.")
        if not target_room.is_vacant:
            raise HTTPException(
                400,
                f"Room {target_room.room_number} is no longer available "
                f"(status: {target_room.status.value}). "
                f"Reject this booking instead.",
            )

    req.status = body.status
    req.reviewed_by = str(current_user.id)
    req.reviewed_at = datetime.utcnow()
    req.review_notes = body.review_notes
    req.updated_at = datetime.utcnow()
    await req.save()

    if body.status == BookingStatus.APPROVED:
        room = await Room.get(PydanticObjectId(req.room_id))
        if room and room.is_vacant:
            # ── 1. Create Tenant profile from booking data (if not exists) ──
            #
            # The `Tenant` collection has *unique* indexes on `phone` and
            # `email`. Naively inserting a new row blows up with a
            # duplicate-key error when an old INACTIVE tenant (or a
            # different user's ACTIVE tenant) already owns the same
            # phone/email. We resolve the existing row with three rules,
            # in order:
            #
            #   1. Same `user_id` -> always reuse (this is the same
            #      person reapplying after being unassigned).
            #   2. Different `user_id` but the existing row is INACTIVE
            #      -> reuse and re-bind. The row is truly orphaned
            #      (previous unassign), so taking it over is safe.
            #   3. Different `user_id` AND the existing row is ACTIVE
            #      -> hard 400 with a clear message. Silently re-binding
            #      an active tenant from another user account would
            #      corrupt their assignment (this is exactly the bug
            #      that left some manager dashboards showing zero
            #      tenants after an approval).
            existing_tenant = await Tenant.find_one({"user_id": req.user_id})

            if not existing_tenant:
                candidate = None
                if req.phone:
                    candidate = await Tenant.find_one({"phone": req.phone})
                if not candidate and req.email:
                    candidate = await Tenant.find_one({"email": req.email})

                if candidate:
                    if candidate.status == TenantStatus.ACTIVE:
                        which = "phone" if (req.phone and candidate.phone == req.phone) else "email"
                        raise HTTPException(
                            400,
                            f"An active tenant already exists with the same {which} "
                            f"({getattr(candidate, which)}). Please reject this booking, "
                            f"ask the applicant to use a different {which}, "
                            f"or unassign the existing tenant first.",
                        )
                    existing_tenant = candidate  # INACTIVE → safe to re-bind

            if existing_tenant:
                # Reuse the row. Always overwrite the assignment-critical
                # fields (`user_id`, `room_id`, `status`, move dates) so
                # the rest of the flow (lease, room update, tenant
                # listing) sees a fully-consistent record.
                existing_tenant.user_id       = req.user_id
                existing_tenant.room_id       = req.room_id
                existing_tenant.status        = TenantStatus.ACTIVE
                existing_tenant.move_in_date  = req.desired_move_in_date or datetime.utcnow()
                existing_tenant.move_out_date = None
                existing_tenant.updated_at    = datetime.utcnow()
                existing_tenant.updated_by    = str(current_user.id)
                await existing_tenant.save()
                tenant = existing_tenant
            else:
                name_parts = req.full_name.strip().split()
                first_name = name_parts[0] if name_parts else req.full_name
                last_name  = req.last_name or (name_parts[-1] if len(name_parts) > 1 else "")

                ec = None
                if req.emergency_contact_name and req.emergency_contact_phone:
                    from models.tenant import EmergencyContact, EmergencyRelation
                    ec = EmergencyContact(
                        full_name    = req.emergency_contact_name,
                        phone        = req.emergency_contact_phone,
                        relationship = EmergencyRelation.OTHER,
                    )

                tenant = Tenant(
                    user_id        = req.user_id,
                    first_name     = first_name,
                    last_name      = last_name,
                    phone          = req.phone,
                    email          = req.email,
                    room_id        = req.room_id,
                    status         = TenantStatus.ACTIVE,
                    move_in_date   = req.desired_move_in_date or datetime.utcnow(),
                    created_by     = str(current_user.id),
                    date_of_birth  = req.date_of_birth,
                    gender         = req.gender,
                    civil_status   = req.civil_status,
                    nationality    = req.nationality or "Filipino",
                    occupation     = req.occupation,
                    employer       = req.employer,
                    monthly_income = req.monthly_income,
                    emergency_contact = ec,
                )
                await tenant.insert()

            # Always update personal details from booking form (in case tenant exists but nulls remain)
            from beanie.operators import Set as BSet
            profile_updates = {}
            if req.date_of_birth and not tenant.date_of_birth:
                profile_updates["date_of_birth"] = req.date_of_birth
            if req.gender and not tenant.gender:
                profile_updates["gender"] = req.gender
            if req.civil_status and not tenant.civil_status:
                profile_updates["civil_status"] = req.civil_status
            if req.occupation and not tenant.occupation:
                profile_updates["occupation"] = req.occupation
            if req.employer and not tenant.employer:
                profile_updates["employer"] = req.employer
            if req.monthly_income and not tenant.monthly_income:
                profile_updates["monthly_income"] = req.monthly_income
            if req.emergency_contact_name and req.emergency_contact_phone and not tenant.emergency_contact:
                from models.tenant import EmergencyContact, EmergencyRelation
                profile_updates["emergency_contact"] = EmergencyContact(
                    full_name    = req.emergency_contact_name,
                    phone        = req.emergency_contact_phone,
                    relationship = EmergencyRelation.OTHER,
                )
            if req.room_id and not tenant.room_id:
                profile_updates["room_id"] = req.room_id
            if profile_updates:
                profile_updates["updated_at"] = datetime.utcnow()
                profile_updates["updated_by"] = str(current_user.id)
                await tenant.update(BSet(profile_updates))

            # ── 2. Create Lease ──
            today = date.today()
            end_dt = date(today.year + 1, today.month, min(today.day, 28))
            lease = Lease(
                tenant_id        = str(tenant.id),
                room_id          = req.room_id,
                start_date       = today,
                end_date         = end_dt,
                status           = LeaseStatus.ACTIVE,
                monthly_rate     = req.monthly_rent,
                payment_frequency= PaymentFrequency.MONTHLY,
                deposit_amount   = req.monthly_rent * 2,
                advance_amount   = req.monthly_rent,
                due_day          = 1,
                created_by       = str(current_user.id),
            )
            await lease.insert()

            # ── 3. Update room ──
            room.status = RoomStatus.OCCUPIED
            room.current_occupants = min(room.current_occupants + 1, room.max_occupants)
            room.updated_at = datetime.utcnow()
            await room.save()

    if body.status == BookingStatus.REJECTED:
        # ── Notify the applicant of rejection ──
        try:
            from models.notification import Notification, NotificationType, NotificationPriority
            reason_text = body.review_notes or "No reason provided."
            notif = Notification(
                recipient_id      = req.user_id,
                sender_id         = str(current_user.id),
                notification_type = NotificationType.ANNOUNCEMENT,
                priority          = NotificationPriority.HIGH,
                title             = f"Booking for Room {req.room_number or req.room_id[:8]} was Rejected",
                message           = f"Your booking application for Room {req.room_number or req.room_id[:8]} has been rejected. "
                                    f"Reason: {reason_text} You may browse other available rooms.",
                reference_id      = str(req.id),
                reference_type    = "booking_request",
            )
            await notif.insert()
        except Exception:
            pass

        # ── Clean up room and tenant if this booking had already reserved/occupied the room ──
        try:
            room = await Room.get(PydanticObjectId(req.room_id))
            if room and room.status in (RoomStatus.RESERVED, RoomStatus.OCCUPIED):
                # Only reset if no other active/approved bookings hold this room
                other_approved = await BookingRequest.find_one({
                    "room_id": req.room_id,
                    "status": BookingStatus.APPROVED.value,
                    "_id": {"$ne": PydanticObjectId(req.id)},
                })
                if not other_approved:
                    room.status = RoomStatus.VACANT
                    room.current_occupants = max(0, room.current_occupants - 1)
                    room.updated_at = datetime.utcnow()
                    await room.save()

            # Deactivate tenant created from this booking (if any)
            tenant = await Tenant.find_one({"user_id": req.user_id, "room_id": req.room_id, "status": TenantStatus.ACTIVE})
            if tenant:
                lease = await Lease.find_one({"tenant_id": str(tenant.id), "room_id": req.room_id, "status": LeaseStatus.ACTIVE})
                if lease:
                    lease.status = LeaseStatus.TERMINATED
                    lease.updated_at = datetime.utcnow()
                    await lease.save()

                tenant.room_id = None
                tenant.status = TenantStatus.INACTIVE
                tenant.move_out_date = datetime.utcnow()
                tenant.updated_at = datetime.utcnow()
                await tenant.save()
        except Exception:
            pass  # cleanup is best-effort; don't fail the rejection

    action_word = "approved" if body.status == BookingStatus.APPROVED else "rejected"
    return {
        "message": f"Booking {action_word} successfully.",
        "booking_id": str(req.id),
        "status": req.status.value,
    }


@router.delete(
    "/manager/{booking_id}",
    summary="Delete a booking request (manager / admin)",
    status_code=status.HTTP_200_OK,
)
async def delete_booking(
    booking_id: str,
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    req = await get_booking_or_404(booking_id)
    await req.delete()
    return {"message": "Booking request deleted successfully."}
