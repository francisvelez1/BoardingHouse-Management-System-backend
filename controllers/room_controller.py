from fastapi import APIRouter, Depends, Query, Path, Body, status
from beanie import PydanticObjectId

from services import room_service
from models.room import RoomStatus, RoomType
from dto.request.room_request import RoomCreateRequest, RoomUpdateRequest
from dto.response.room_response import RoomResponse
from dto.response.api_response import ApiResponse
from config.jwt_middleware import get_current_user, require_roles
from models.user import RoleName

router = APIRouter(
    prefix="/api/rooms",
    tags=["Rooms"],
)


# ================================================================
# POST /api/rooms
# ================================================================

@router.post(
    "/",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new room",
    description="Adds a new room to the boarding house. "
                "New rooms always start with VACANT status. "
                "Accessible by ADMIN and MANAGER only.",
)
async def create_room(
    request: RoomCreateRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.create_room(
        request=request,
        created_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Room created successfully.",
        status_code=status.HTTP_201_CREATED,
    )


# ================================================================
# GET /api/rooms
# ================================================================

@router.get(
    "/",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get all rooms",
    description="Returns a paginated list of all rooms. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_all_rooms(
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_all_rooms(skip=skip, limit=limit)
    return ApiResponse.success(
        data=data,
        message="Rooms retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/search
# ================================================================

@router.get(
    "/search",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Search rooms",
    description="Search rooms by room number or description. "
                "Case-insensitive. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def search_rooms(
    q:     str = Query(..., min_length=1, description="Search keyword"),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.search_rooms(
        query=q, skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message=f"Search results for '{q}'.",
    )


# ================================================================
# GET /api/rooms/stats
# ================================================================

@router.get(
    "/stats",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Get room statistics",
    description="Returns room counts grouped by status and occupancy rate. "
                "Used by the dashboard stats grid. "
                "Accessible by ADMIN and MANAGER.",
)
async def get_room_stats(
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.get_room_stats()
    return ApiResponse.success(
        data=data,
        message="Room statistics retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/vacant
# ================================================================

@router.get(
    "/vacant",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get all vacant rooms",
    description="Returns all rooms with VACANT status. "
                "Used by room selection UI when assigning a tenant. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_vacant_rooms(
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_vacant_rooms(skip=skip, limit=limit)
    return ApiResponse.success(
        data=data,
        message="Vacant rooms retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/maintenance
# ================================================================

@router.get(
    "/maintenance",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get rooms under maintenance",
    description="Returns all rooms currently under maintenance. "
                "Used by the maintenance dashboard. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_rooms_under_maintenance(
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_rooms_under_maintenance(
        skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message="Rooms under maintenance retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/status/{room_status}
# ================================================================

@router.get(
    "/status/{room_status}",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get rooms by status",
    description="Returns rooms filtered by status: "
                "VACANT, OCCUPIED, MAINTENANCE, or RESERVED. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_rooms_by_status(
    room_status: RoomStatus = Path(..., description="Room status filter"),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_rooms_by_status(
        status=room_status, skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message=f"Rooms with status '{room_status.value}' retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/type/{room_type}
# ================================================================

@router.get(
    "/type/{room_type}",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get rooms by type",
    description="Returns rooms filtered by type: "
                "SINGLE, DOUBLE, STUDIO, DORMITORY, or SUITE. "
                "Accessible by ADMIN, MANAGER, STAFF, and TENANT.",
)
async def get_rooms_by_type(
    room_type: RoomType = Path(..., description="Room type filter"),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER,
        RoleName.STAFF, RoleName.TENANT,
    )),
):
    data = await room_service.get_rooms_by_type(
        room_type=room_type, skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message=f"Rooms of type '{room_type.value}' retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/rate-range
# ================================================================

@router.get(
    "/rate-range",
    response_model=ApiResponse[list[RoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get rooms by rate range",
    description="Returns rooms within a monthly rate range (PHP). "
                "Accessible by ADMIN, MANAGER, STAFF, and TENANT.",
)
async def get_rooms_by_rate_range(
    min_rate: float = Query(..., ge=0,   description="Minimum monthly rate in PHP"),
    max_rate: float = Query(..., gt=0,   description="Maximum monthly rate in PHP"),
    skip:     int   = Query(default=0,  ge=0),
    limit:    int   = Query(default=20, ge=1, le=100),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER,
        RoleName.STAFF, RoleName.TENANT,
    )),
):
    data = await room_service.get_rooms_by_rate_range(
        min_rate=min_rate, max_rate=max_rate, skip=skip, limit=limit
    )
    return ApiResponse.success(
        data=data,
        message=f"Rooms between ₱{min_rate:,.2f} and ₱{max_rate:,.2f} retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/number/{room_number}
# ================================================================

@router.get(
    "/number/{room_number}",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Get room by room number",
    description="Returns a single room by its room number (e.g. '101', '2A'). "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_room_by_number(
    room_number: str = Path(..., description="Room number string"),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_room_by_number(room_number)
    return ApiResponse.success(
        data=data,
        message="Room retrieved successfully.",
    )


# ================================================================
# GET /api/rooms/{room_id}
# ================================================================

@router.get(
    "/{room_id}",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Get room by ID",
    description="Returns a single room by its MongoDB ObjectId. "
                "Accessible by ADMIN, MANAGER, and STAFF.",
)
async def get_room_by_id(
    room_id: PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.STAFF
    )),
):
    data = await room_service.get_room_by_id(room_id)
    return ApiResponse.success(
        data=data,
        message="Room retrieved successfully.",
    )


# ================================================================
# PATCH /api/rooms/{room_id}
# ================================================================

@router.patch(
    "/{room_id}",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Update room details",
    description="Partially updates a room's details. "
                "Only fields included in the request body are updated. "
                "Accessible by ADMIN and MANAGER.",
)
async def update_room(
    room_id: PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    request: RoomUpdateRequest = Body(...),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.update_room(
        room_id=room_id,
        request=request,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Room updated successfully.",
    )


# ================================================================
# PATCH /api/rooms/{room_id}/status
# ================================================================

@router.patch(
    "/{room_id}/status",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Update room status",
    description="Updates a room's status to VACANT, MAINTENANCE, or RESERVED. "
                "Cannot manually set to OCCUPIED — use LeaseService instead. "
                "Accessible by ADMIN and MANAGER.",
)
async def update_room_status(
    room_id:     PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    room_status: RoomStatus       = Body(..., embed=True, alias="status"),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.update_room_status(
        room_id=room_id,
        status=room_status,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message=f"Room status updated to '{room_status.value}'.",
    )


# ================================================================
# PATCH /api/rooms/{room_id}/maintenance/start
# ================================================================

@router.patch(
    "/{room_id}/maintenance/start",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Start room maintenance",
    description="Flags a room as under maintenance. "
                "Room must not be currently occupied. "
                "Accessible by ADMIN, MANAGER, and MAINTENANCE.",
)
async def start_maintenance(
    room_id: PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    maintenance_notes: str    = Body(..., embed=True),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.MAINTENANCE
    )),
):
    data = await room_service.set_room_under_maintenance(
        room_id=room_id,
        maintenance_notes=maintenance_notes,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Room has been flagged for maintenance.",
    )


# ================================================================
# PATCH /api/rooms/{room_id}/maintenance/complete
# ================================================================

@router.patch(
    "/{room_id}/maintenance/complete",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Complete room maintenance",
    description="Marks room maintenance as complete and sets status back to VACANT. "
                "Room must currently be in MAINTENANCE status. "
                "Accessible by ADMIN, MANAGER, and MAINTENANCE.",
)
async def complete_maintenance(
    room_id: PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    current_user=Depends(require_roles(
        RoleName.ADMIN, RoleName.MANAGER, RoleName.MAINTENANCE
    )),
):
    data = await room_service.complete_room_maintenance(
        room_id=room_id,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Room maintenance completed. Room is now VACANT.",
    )


# ================================================================
# POST /api/rooms/{room_id}/images
# ================================================================

@router.post(
    "/{room_id}/images",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Add room image",
    description="Adds an image URL to the room's image list. "
                "image_url should be provided by FileStorageService after upload. "
                "Accessible by ADMIN and MANAGER.",
)
async def add_room_image(
    room_id:   PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    image_url: str              = Body(..., embed=True),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.add_room_image(
        room_id=room_id,
        image_url=image_url,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Image added to room successfully.",
    )


# ================================================================
# DELETE /api/rooms/{room_id}/images
# ================================================================

@router.delete(
    "/{room_id}/images",
    response_model=ApiResponse[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove room image",
    description="Removes an image URL from the room's image list. "
                "Accessible by ADMIN and MANAGER.",
)
async def remove_room_image(
    room_id:   PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    image_url: str              = Body(..., embed=True),
    current_user=Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER)),
):
    data = await room_service.remove_room_image(
        room_id=room_id,
        image_url=image_url,
        updated_by=current_user["username"],
    )
    return ApiResponse.success(
        data=data,
        message="Image removed from room successfully.",
    )


# ================================================================
# DELETE /api/rooms/{room_id}
# ================================================================

@router.delete(
    "/{room_id}",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete room",
    description="Permanently deletes a room record. "
                "Room must not be currently occupied. "
                "Prefer setting status to MAINTENANCE instead. "
                "Accessible by ADMIN only.",
)
async def delete_room(
    room_id: PydanticObjectId = Path(..., description="Room MongoDB ObjectId"),
    current_user=Depends(require_roles(RoleName.ADMIN)),
):
    data = await room_service.delete_room(room_id)
    return ApiResponse.success(
        data=data,
        message=data.get("message", "Room deleted successfully."),
    )