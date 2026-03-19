
from fastapi import APIRouter, Depends, Query, Path, Body, status
from beanie import PydanticObjectId
from datetime import datetime
from typing import Optional

from services import tenant_service
from models.tenant import TenantStatus
from dto.request.tenant_request import (
    TenantCreateRequest,
    TenantUpdateRequest,
    AssignRoomRequest,
    DepositPaymentRequest,
)
from dto.response.tenant_response import TenantResponse
from dto.response.api_response import ApiResponse
from config.jwt_middleware import get_current_user, require_roles
from models.user import RoleName

router = APIRouter(
    prefix="/api/tenants",
    tags=["Tenants"],
)


# ================================================================
# POST /api/tenants
# ================================================================

@router.post(
    "/",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant",
    description="Creates a new tenant profile linked to an existing User account. "
                "Status is set to PENDING until a room is assigned. "
                "Accessible by ADMIN and MANAGER only.",
)
async def register_tenant(
    request: TenantCreateRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.register_tenant(
        request=request,
        created_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Tenant registered successfully.",
        status_code=status.HTTP_201_CREATED,
    )


# ================================================================
# GET /api/tenants
# ================================================================

@router.get(
    "/",
    response_model=ApiResponse[list[TenantResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get all tenants",
    description="Returns a paginated list of all tenants. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_all_tenants(
    skip:  int = Query(default=0,  ge=0,   description="Number of records to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF)),
):
    data = await tenant_service.get_all_tenants(skip=skip, limit=limit)
    return ApiResponse.success(
        data=data,
        message="Tenants retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/search
# ================================================================

@router.get(
    "/search",
    response_model=ApiResponse[list[TenantResponse]],
    status_code=status.HTTP_200_OK,
    summary="Search tenants",
    description="Search tenants by name, email, or phone number. "
                "Case-insensitive. Accessible by ADMIN, MANAGER, and STAFF.",
)
async def search_tenants(
    q:     str = Query(..., min_length=1, description="Search keyword"),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF)),
):
    data = await tenant_service.search_tenants(query=q, skip=skip, limit=limit)
    return ApiResponse.success(
        data=data,
        message=f"Search results for '{q}'.",
    )


# ================================================================
# GET /api/tenants/stats
# ================================================================

@router.get(
    "/stats",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Get tenant statistics",
    description="Returns tenant counts grouped by status. "
                "Used by the dashboard stats grid. "
                "Accessible by ADMIN and MANAGER.",
)
async def get_tenant_stats(
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.get_tenant_stats()
    return ApiResponse.success(
        data=data,
        message="Tenant statistics retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/status/{status}
# ================================================================

@router.get(
    "/status/{tenant_status}",
    response_model=ApiResponse[list[TenantResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get tenants by status",
    description="Returns tenants filtered by status: "
                "ACTIVE, PENDING, INACTIVE, or MOVED_OUT. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_tenants_by_status(
    tenant_status: TenantStatus = Path(..., description="Tenant status filter"),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF)),
):
    data = await tenant_service.get_tenants_by_status(
        status=tenant_status, skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message=f"Tenants with status '{tenant_status.value}' retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/unverified
# ================================================================

@router.get(
    "/unverified",
    response_model=ApiResponse[list[TenantResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get tenants with unverified IDs",
    description="Returns tenants who have submitted a government ID "
                "but have not yet been verified by staff. "
                "Accessible by ADMIN and MANAGER.",
)
async def get_unverified_tenants(
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.get_unverified_tenants(skip=skip, limit=limit)
    return ApiResponse.success(
        data=data,
        message="Unverified tenants retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/outstanding-balance
# ================================================================

@router.get(
    "/outstanding-balance",
    response_model=ApiResponse[list[TenantResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get tenants with outstanding balance",
    description="Returns tenants who have unpaid balances. "
                "Used by BillingService for payment reminders. "
                "Accessible by ADMIN and MANAGER.",
)
async def get_tenants_with_outstanding_balance(
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.get_tenants_with_outstanding_balance(
        skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message="Tenants with outstanding balance retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/me  (tenant views their own profile)
# ================================================================

@router.get(
    "/me",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Get my tenant profile",
    description="Returns the tenant profile of the currently logged-in user. "
                "Accessible by TENANT role only.",
)
async def get_my_profile(
    current_user=Depends(require_roles(RoleName.TENANT)),
):
    data = await tenant_service.get_tenant_by_user_id(current_user.id)
    return ApiResponse.success(
        data=data,
        message="Your tenant profile retrieved successfully.",
    )


# ================================================================
# GET /api/tenants/{tenant_id}
# ================================================================

@router.get(
    "/{tenant_id}",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Get tenant by ID",
    description="Returns a single tenant by their MongoDB ObjectId. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_tenant_by_id(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF)),
):
    data = await tenant_service.get_tenant_by_id(tenant_id)
    return ApiResponse.success(
        data=data,
        message="Tenant retrieved successfully.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}
# ================================================================

@router.patch(
    "/{tenant_id}",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Update tenant profile",
    description="Partially updates a tenant's profile. "
                "Only fields included in the request body are updated. "
                "Accessible by ADMIN and MANAGER.",
)
async def update_tenant(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    request: TenantUpdateRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.update_tenant(
        tenant_id=tenant_id,
        request=request,
        updated_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Tenant updated successfully.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}/status
# ================================================================

@router.patch(
    "/{tenant_id}/status",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Update tenant status",
    description="Updates a tenant's status to ACTIVE, INACTIVE, "
                "PENDING, or MOVED_OUT. "
                "Accessible by ADMIN and MANAGER.",
)
async def update_tenant_status(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    tenant_status: TenantStatus = Body(..., embed=True, alias="status"),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.update_tenant_status(
        tenant_id=tenant_id,
        status=tenant_status,
        updated_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message=f"Tenant status updated to '{tenant_status.value}'.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}/assign-room
# ================================================================

@router.patch(
    "/{tenant_id}/assign-room",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Assign room to tenant",
    description="Assigns a room to a tenant and sets their status to ACTIVE. "
                "Room must be vacant. "
                "Accessible by ADMIN and MANAGER.",
)
async def assign_room(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    request: AssignRoomRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.assign_room_to_tenant(
        tenant_id=tenant_id,
        room_id=request.room_id,
        move_in_date=request.move_in_date,
        updated_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Room assigned to tenant successfully.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}/unassign-room
# ================================================================

@router.patch(
    "/{tenant_id}/unassign-room",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Unassign room from tenant",
    description="Removes a tenant's room assignment and sets their "
                "status to MOVED_OUT. Records the move-out date. "
                "Accessible by ADMIN and MANAGER.",
)
async def unassign_room(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    move_out_date: datetime = Body(..., embed=True),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.unassign_room_from_tenant(
        tenant_id=tenant_id,
        move_out_date=move_out_date,
        updated_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Room unassigned from tenant successfully.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}/verify-id
# ================================================================

@router.patch(
    "/{tenant_id}/verify-id",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Verify tenant government ID",
    description="Marks a tenant's submitted government ID as verified "
                "after manual staff review. "
                "Accessible by ADMIN and MANAGER.",
)
async def verify_tenant_id(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.verify_tenant_id(
        tenant_id=tenant_id,
        verified_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Tenant government ID verified successfully.",
    )


# ================================================================
# PATCH /api/tenants/{tenant_id}/deposit
# ================================================================

@router.patch(
    "/{tenant_id}/deposit",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_200_OK,
    summary="Record security deposit payment",
    description="Records that a tenant has paid their security deposit. "
                "Accessible by ADMIN and MANAGER.",
)
async def record_deposit(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    request: DepositPaymentRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await tenant_service.record_deposit_payment(
        tenant_id=tenant_id,
        amount=request.amount,
        deposit_date=request.deposit_date,
        updated_by=current_user.username,
    )
    return ApiResponse.success(
        data=data,
        message="Security deposit recorded successfully.",
    )


# ================================================================
# DELETE /api/tenants/{tenant_id}
# ================================================================

@router.delete(
    "/{tenant_id}",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete tenant",
    description="Permanently deletes a tenant record. "
                "Tenant must not be occupying a room or have outstanding balance. "
                "Prefer setting status to INACTIVE instead. "
                "Accessible by ADMIN only.",
)
async def delete_tenant(
    tenant_id: PydanticObjectId = Path(..., description="Tenant MongoDB ObjectId"),
    current_user=Depends(require_roles(RoleName.ADMIN)),
):
    data = await tenant_service.delete_tenant(tenant_id)
    return ApiResponse.success(
        data=data,
        message=data.get("message", "Tenant deleted successfully."),
    )