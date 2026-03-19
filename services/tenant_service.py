
from beanie import PydanticObjectId
from datetime import datetime
from typing import Optional

from models.tenant import (
    Tenant,
    TenantStatus,
    GovernmentID,
    EmergencyContact,
    Address,
)
from repository import tenant_repository, room_repository, user_repository
from dto.request.tenant_request import TenantCreateRequest, TenantUpdateRequest
from dto.response.tenant_response import TenantResponse
from exception.resource_not_found_exception import ResourceNotFoundException
from exception.bad_request_exception import BadRequestException
from exception.duplicate_resource_exception import DuplicateResourceException


# ================================================================
# INTERNAL HELPERS  (private — not called from controllers)
# ================================================================

async def _assert_tenant_exists(tenant_id: PydanticObjectId) -> Tenant:
    """
    Fetches a tenant or raises 404.
    Used internally to avoid repeating the None-check pattern.
    """
    tenant = await tenant_repository.get_tenant_by_id(tenant_id)
    if not tenant:
        raise ResourceNotFoundException(f"Tenant not found: {tenant_id}")
    return tenant


async def _assert_no_duplicate_email(email: str, exclude_id: Optional[PydanticObjectId] = None) -> None:
    """
    Raises 409 if the email is already registered to another tenant.
    Pass exclude_id when updating so the tenant's own email is not flagged.
    """
    existing = await tenant_repository.get_tenant_by_email(email)
    if existing and existing.id != exclude_id:
        raise DuplicateResourceException(f"Email already registered to another tenant: {email}")


async def _assert_no_duplicate_phone(phone: str, exclude_id: Optional[PydanticObjectId] = None) -> None:
    """
    Raises 409 if the phone number is already registered to another tenant.
    """
    existing = await tenant_repository.get_tenant_by_phone(phone)
    if existing and existing.id != exclude_id:
        raise DuplicateResourceException(f"Phone already registered to another tenant: {phone}")


async def _assert_room_is_vacant(room_id: PydanticObjectId) -> None:
    """
    Raises 400 if the target room is already occupied by an active tenant.
    """
    occupant = await tenant_repository.get_tenant_by_room(room_id)
    if occupant:
        raise BadRequestException(
            f"Room {room_id} is already occupied by tenant: {occupant.full_name}"
        )


async def _assert_room_exists(room_id: PydanticObjectId) -> None:
    """
    Raises 404 if the room does not exist in the database.
    """
    room = await room_repository.get_room_by_id(room_id)
    if not room:
        raise ResourceNotFoundException(f"Room not found: {room_id}")


async def _assert_user_exists(user_id: PydanticObjectId) -> None:
    """
    Raises 404 if the linked User account does not exist.
    """
    user = await user_repository.get_user_by_id(user_id)
    if not user:
        raise ResourceNotFoundException(f"User not found: {user_id}")


async def _assert_no_existing_tenant_profile(user_id: PydanticObjectId) -> None:
    """
    Raises 400 if a tenant profile already exists for this User account.
    One User account must map to exactly one Tenant profile.
    """
    existing = await tenant_repository.get_tenant_by_user_id(user_id)
    if existing:
        raise BadRequestException(
            f"A tenant profile already exists for user: {user_id}"
        )


def _build_tenant_from_request(
    request: TenantCreateRequest,
    created_by: str
) -> Tenant:
    """
    Constructs a Tenant document from a validated create request.
    Does not persist — caller must call create_tenant() after.
    """
    government_id = None
    if request.government_id:
        government_id = GovernmentID(
            id_type=request.government_id.id_type,
            id_number=request.government_id.id_number,
            issued_date=request.government_id.issued_date,
            expiry_date=request.government_id.expiry_date,
        )

    emergency_contact = None
    if request.emergency_contact:
        emergency_contact = EmergencyContact(
            full_name=request.emergency_contact.full_name,
            phone=request.emergency_contact.phone,
            relationship=request.emergency_contact.relationship,
            email=request.emergency_contact.email,
            address=request.emergency_contact.address,
        )

    home_address = None
    if request.home_address:
        home_address = Address(
            street=request.home_address.street,
            barangay=request.home_address.barangay,
            city=request.home_address.city,
            province=request.home_address.province,
            zip_code=request.home_address.zip_code,
            country=request.home_address.country,
        )

    return Tenant(
        user_id=request.user_id,
        first_name=request.first_name,
        last_name=request.last_name,
        middle_name=request.middle_name,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        civil_status=request.civil_status,
        nationality=request.nationality,
        phone=request.phone,
        email=request.email,
        occupation=request.occupation,
        employer=request.employer,
        monthly_income=request.monthly_income,
        government_id=government_id,
        emergency_contact=emergency_contact,
        home_address=home_address,
        status=TenantStatus.PENDING,
        created_by=created_by,
        updated_by=created_by,
    )


# ================================================================
# CREATE
# ================================================================

async def register_tenant(
    request: TenantCreateRequest,
    created_by: str
) -> TenantResponse:
    """
    Registers a new tenant profile.

    Validations:
    - Linked User must exist
    - User must not already have a tenant profile
    - Email and phone must be unique across all tenants

    Status is set to PENDING until staff approves and assigns a room.
    """
    await _assert_user_exists(request.user_id)
    await _assert_no_existing_tenant_profile(request.user_id)
    await _assert_no_duplicate_email(request.email)
    await _assert_no_duplicate_phone(request.phone)

    tenant = _build_tenant_from_request(request, created_by)
    created = await tenant_repository.create_tenant(tenant)
    return TenantResponse.from_tenant(created)


# ================================================================
# READ
# ================================================================

async def get_all_tenants(
    skip: int = 0,
    limit: int = 20
) -> list[TenantResponse]:
    """
    Returns a paginated list of all tenants.
    """
    tenants = await tenant_repository.get_all_tenants(skip=skip, limit=limit)
    return [TenantResponse.from_tenant(t) for t in tenants]


async def get_tenant_by_id(tenant_id: PydanticObjectId) -> TenantResponse:
    """
    Returns a single tenant by ID.
    Raises 404 if not found.
    """
    tenant = await _assert_tenant_exists(tenant_id)
    return TenantResponse.from_tenant(tenant)


async def get_tenant_by_user_id(user_id: PydanticObjectId) -> TenantResponse:
    """
    Returns the tenant profile linked to a User account.
    Raises 404 if no tenant profile exists for this user.
    """
    tenant = await tenant_repository.get_tenant_by_user_id(user_id)
    if not tenant:
        raise ResourceNotFoundException(f"No tenant profile found for user: {user_id}")
    return TenantResponse.from_tenant(tenant)


async def get_tenants_by_status(
    status: TenantStatus,
    skip: int = 0,
    limit: int = 20
) -> list[TenantResponse]:
    """
    Returns tenants filtered by status (ACTIVE, PENDING, MOVED_OUT, INACTIVE).
    """
    tenants = await tenant_repository.get_tenants_by_status(
        status=status, skip=skip, limit=limit
    )
    return [TenantResponse.from_tenant(t) for t in tenants]


async def get_tenants_with_outstanding_balance(
    skip: int = 0,
    limit: int = 20
) -> list[TenantResponse]:
    """
    Returns tenants who have unpaid balances.
    Used by BillingService for payment reminder scheduling.
    """
    tenants = await tenant_repository.get_tenants_with_outstanding_balance(
        skip=skip, limit=limit
    )
    return [TenantResponse.from_tenant(t) for t in tenants]


async def get_unverified_tenants(
    skip: int = 0,
    limit: int = 20
) -> list[TenantResponse]:
    """
    Returns tenants with unverified government IDs.
    Used by admin dashboard for the ID review queue.
    """
    tenants = await tenant_repository.get_unverified_tenants(
        skip=skip, limit=limit
    )
    return [TenantResponse.from_tenant(t) for t in tenants]


async def search_tenants(
    query: str,
    skip: int = 0,
    limit: int = 20
) -> list[TenantResponse]:
    """
    Searches tenants by name, email, or phone.
    Raises 400 if the search query is empty.
    """
    if not query or not query.strip():
        raise BadRequestException("Search query must not be empty.")

    tenants = await tenant_repository.search_tenants(
        query=query.strip(), skip=skip, limit=limit
    )
    return [TenantResponse.from_tenant(t) for t in tenants]


async def get_tenant_stats() -> dict:
    """
    Returns a summary of tenant counts grouped by status.
    Used by DashboardService for the stats grid.
    """
    total    = await tenant_repository.count_all_tenants()
    active   = await tenant_repository.count_tenants_by_status(TenantStatus.ACTIVE)
    pending  = await tenant_repository.count_tenants_by_status(TenantStatus.PENDING)
    inactive = await tenant_repository.count_tenants_by_status(TenantStatus.INACTIVE)
    moved_out= await tenant_repository.count_tenants_by_status(TenantStatus.MOVED_OUT)

    return {
        "total":     total,
        "active":    active,
        "pending":   pending,
        "inactive":  inactive,
        "moved_out": moved_out,
    }


# ================================================================
# UPDATE
# ================================================================

async def update_tenant(
    tenant_id: PydanticObjectId,
    request: TenantUpdateRequest,
    updated_by: str
) -> TenantResponse:
    """
    Partially updates a tenant's profile fields.

    Only fields present in the request are updated.
    Email and phone uniqueness are re-validated if changed.
    """
    tenant = await _assert_tenant_exists(tenant_id)

    updates: dict = {}

    if request.first_name   is not None: updates["first_name"]   = request.first_name
    if request.last_name    is not None: updates["last_name"]    = request.last_name
    if request.middle_name  is not None: updates["middle_name"]  = request.middle_name
    if request.date_of_birth is not None: updates["date_of_birth"] = request.date_of_birth
    if request.gender       is not None: updates["gender"]       = request.gender
    if request.civil_status is not None: updates["civil_status"] = request.civil_status
    if request.nationality  is not None: updates["nationality"]  = request.nationality
    if request.occupation   is not None: updates["occupation"]   = request.occupation
    if request.employer     is not None: updates["employer"]     = request.employer
    if request.monthly_income is not None: updates["monthly_income"] = request.monthly_income
    if request.notes        is not None: updates["notes"]        = request.notes

    if request.phone is not None and request.phone != tenant.phone:
        await _assert_no_duplicate_phone(request.phone, exclude_id=tenant_id)
        updates["phone"] = request.phone

    if request.email is not None and request.email != tenant.email:
        await _assert_no_duplicate_email(request.email, exclude_id=tenant_id)
        updates["email"] = request.email

    if request.home_address is not None:
        updates["home_address"] = Address(
            street=request.home_address.street,
            barangay=request.home_address.barangay,
            city=request.home_address.city,
            province=request.home_address.province,
            zip_code=request.home_address.zip_code,
            country=request.home_address.country,
        ).model_dump()

    if request.emergency_contact is not None:
        updates["emergency_contact"] = EmergencyContact(
            full_name=request.emergency_contact.full_name,
            phone=request.emergency_contact.phone,
            relationship=request.emergency_contact.relationship,
            email=request.emergency_contact.email,
            address=request.emergency_contact.address,
        ).model_dump()

    if request.government_id is not None:
        updates["government_id"] = GovernmentID(
            id_type=request.government_id.id_type,
            id_number=request.government_id.id_number,
            issued_date=request.government_id.issued_date,
            expiry_date=request.government_id.expiry_date,
            verified=False,       # Reset verification on ID re-submission
            verified_by=None,
            verified_at=None,
        ).model_dump()

    if not updates:
        raise BadRequestException("No valid fields provided for update.")

    updated = await tenant_repository.update_tenant(
        tenant_id=tenant_id,
        updates=updates,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


async def update_tenant_status(
    tenant_id: PydanticObjectId,
    status: TenantStatus,
    updated_by: str
) -> TenantResponse:
    """
    Updates the status of a tenant directly.

    Rules:
    - Cannot set ACTIVE unless a room is assigned
    - Cannot set PENDING if tenant already has a room
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if status == TenantStatus.ACTIVE and not tenant.is_occupying:
        raise BadRequestException(
            "Cannot set tenant to ACTIVE without an assigned room. "
            "Use assign_room_to_tenant() instead."
        )

    if status == TenantStatus.PENDING and tenant.is_occupying:
        raise BadRequestException(
            "Cannot set an occupying tenant back to PENDING. "
            "Unassign their room first."
        )

    updated = await tenant_repository.update_tenant_status(
        tenant_id=tenant_id,
        status=status,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


async def update_profile_picture(
    tenant_id: PydanticObjectId,
    filepath_or_url: str,
    updated_by: str
) -> TenantResponse:
    """
    Updates the tenant's profile picture.
    filepath_or_url should come from FileStorageService after upload.
    """
    await _assert_tenant_exists(tenant_id)

    updated = await tenant_repository.update_profile_picture(
        tenant_id=tenant_id,
        filepath_or_url=filepath_or_url,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


# ================================================================
# ROOM ASSIGNMENT
# ================================================================

async def assign_room_to_tenant(
    tenant_id: PydanticObjectId,
    room_id: PydanticObjectId,
    move_in_date: datetime,
    updated_by: str
) -> TenantResponse:
    """
    Assigns a room to a tenant and activates them.

    Validations:
    - Tenant must exist
    - Tenant must not already be occupying a room
    - Room must exist
    - Room must be vacant (no active tenant assigned)

    Sets status to ACTIVE and records move_in_date.
    Should be called by LeaseService when a lease is created —
    not directly from a controller.
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if tenant.is_occupying:
        raise BadRequestException(
            f"Tenant {tenant.full_name} is already assigned to a room. "
            "Unassign current room before reassigning."
        )

    await _assert_room_exists(room_id)
    await _assert_room_is_vacant(room_id)

    updated = await tenant_repository.assign_room(
        tenant_id=tenant_id,
        room_id=room_id,
        move_in_date=move_in_date,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


async def unassign_room_from_tenant(
    tenant_id: PydanticObjectId,
    move_out_date: datetime,
    updated_by: str
) -> TenantResponse:
    """
    Removes the room assignment from a tenant on move-out.

    Validations:
    - Tenant must exist
    - Tenant must currently be occupying a room

    Sets status to MOVED_OUT and records move_out_date.
    Should be called by LeaseService on lease termination —
    not directly from a controller.
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if not tenant.is_occupying:
        raise BadRequestException(
            f"Tenant {tenant.full_name} is not currently assigned to any room."
        )

    updated = await tenant_repository.unassign_room(
        tenant_id=tenant_id,
        move_out_date=move_out_date,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


# ================================================================
# FINANCIAL
# ================================================================

async def record_deposit_payment(
    tenant_id: PydanticObjectId,
    amount: float,
    deposit_date: datetime,
    updated_by: str
) -> TenantResponse:
    """
    Records that a tenant has paid their security deposit.

    Validations:
    - Tenant must exist
    - Deposit must not already be recorded as paid
    - Amount must be greater than zero
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if tenant.deposit_paid:
        raise BadRequestException(
            f"Deposit already recorded for tenant: {tenant.full_name}"
        )

    if amount <= 0:
        raise BadRequestException("Deposit amount must be greater than zero.")

    updated = await tenant_repository.record_deposit(
        tenant_id=tenant_id,
        amount=amount,
        deposit_date=deposit_date,
        updated_by=updated_by
    )
    return TenantResponse.from_tenant(updated)


async def update_tenant_balance(
    tenant_id: PydanticObjectId,
    outstanding_balance: float,
    total_paid: float
) -> TenantResponse:
    """
    Updates the tenant's financial summary.
    Called exclusively by BillingService and PaymentService.
    Do NOT call this from a controller directly.
    """
    await _assert_tenant_exists(tenant_id)

    if outstanding_balance < 0:
        raise BadRequestException("Outstanding balance cannot be negative.")

    if total_paid < 0:
        raise BadRequestException("Total paid cannot be negative.")

    updated = await tenant_repository.update_balance(
        tenant_id=tenant_id,
        outstanding_balance=outstanding_balance,
        total_paid=total_paid
    )
    return TenantResponse.from_tenant(updated)


# ================================================================
# ID VERIFICATION
# ================================================================

async def verify_tenant_id(
    tenant_id: PydanticObjectId,
    verified_by: str
) -> TenantResponse:
    """
    Marks a tenant's government ID as verified after manual staff review.

    Validations:
    - Tenant must exist
    - Tenant must have submitted a government ID
    - ID must not already be verified
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if not tenant.government_id:
        raise BadRequestException(
            f"Tenant {tenant.full_name} has not submitted a government ID."
        )

    if tenant.is_id_verified:
        raise BadRequestException(
            f"Government ID for tenant {tenant.full_name} is already verified."
        )

    updated = await tenant_repository.verify_government_id(
        tenant_id=tenant_id,
        verified_by=verified_by
    )
    return TenantResponse.from_tenant(updated)


# ================================================================
# DELETE
# ================================================================

async def delete_tenant(tenant_id: PydanticObjectId) -> dict:
    """
    Hard deletes a tenant record.

    WARNING: Prefer updating status to INACTIVE or MOVED_OUT.
    Only use this for test data cleanup or admin corrections.
    Active tenants with rooms or outstanding balances should
    never be hard deleted.

    Validations:
    - Tenant must exist
    - Tenant must not be currently occupying a room
    - Tenant must have zero outstanding balance
    """
    tenant = await _assert_tenant_exists(tenant_id)

    if tenant.is_occupying:
        raise BadRequestException(
            f"Cannot delete tenant {tenant.full_name} while they are assigned to a room. "
            "Unassign the room first."
        )

    if tenant.has_outstanding_balance:
        raise BadRequestException(
            f"Cannot delete tenant {tenant.full_name} with an outstanding balance "
            f"of ₱{tenant.outstanding_balance:,.2f}. Settle the balance first."
        )

    deleted = await tenant_repository.delete_tenant(tenant_id)
    if not deleted:
        raise ResourceNotFoundException(f"Tenant not found: {tenant_id}")

    return {"message": f"Tenant {tenant.full_name} has been permanently deleted."}