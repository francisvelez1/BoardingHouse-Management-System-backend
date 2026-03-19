# ============================================================
# services/room_service.py
# ResidEase – Boarding House Management System
# ============================================================

from beanie import PydanticObjectId
from datetime import datetime
from typing import Optional

from models.room import Room, RoomStatus, RoomType, RoomAmenity, RoomDimension
from repository import room_repository
from dto.request.room_request import RoomCreateRequest, RoomUpdateRequest
from dto.response.room_response import RoomResponse
from exception.resource_not_found_exception import ResourceNotFoundException
from exception.bad_request_exception import BadRequestException
from exception.duplicate_resource_exception import DuplicateResourceException


# ================================================================
# INTERNAL HELPERS
# ================================================================

async def _assert_room_exists(room_id: PydanticObjectId) -> Room:
    """
    Fetches a room or raises 404.
    """
    room = await room_repository.get_room_by_id(room_id)
    if not room:
        raise ResourceNotFoundException(f"Room not found: {room_id}")
    return room


async def _assert_no_duplicate_room_number(
    room_number: str,
    exclude_id: Optional[PydanticObjectId] = None,
) -> None:
    """
    Raises 409 if the room number is already taken by another room.
    Pass exclude_id when updating so the room's own number is not flagged.
    """
    existing = await room_repository.get_room_by_number(room_number)
    if existing and existing.id != exclude_id:
        raise DuplicateResourceException(
            f"Room number '{room_number}' already exists."
        )


def _assert_rate_is_positive(rate: float) -> None:
    """Raises 400 if monthly rate is zero or negative."""
    if rate <= 0:
        raise BadRequestException("Monthly rate must be greater than zero.")


def _assert_occupants_within_capacity(room: Room) -> None:
    """
    Raises 400 if the room has reached its maximum occupant capacity.
    Called before assigning a new tenant to a room.
    """
    if room.is_full:
        raise BadRequestException(
            f"Room {room.room_number} has reached its maximum capacity "
            f"of {room.max_occupants} occupant(s)."
        )


def _build_room_from_request(
    request: RoomCreateRequest,
    created_by: str,
) -> Room:
    """
    Constructs a Room document from a validated create request.
    Does not persist — caller must call create_room() after.
    """
    dimension = None
    if request.dimension:
        dimension = RoomDimension(
            length_sqm=request.dimension.length_sqm,
            width_sqm=request.dimension.width_sqm,
        )

    amenities = []
    if request.amenities:
        amenities = [
            RoomAmenity(
                name=a.name,
                description=a.description,
                is_working=a.is_working,
            )
            for a in request.amenities
        ]

    return Room(
        room_number=request.room_number,
        floor_level=request.floor_level,
        room_type=request.room_type,
        description=request.description,
        max_occupants=request.max_occupants,
        monthly_rate=request.monthly_rate,
        deposit_multiplier=request.deposit_multiplier,
        advance_multiplier=request.advance_multiplier,
        dimension=dimension,
        amenities=amenities,
        status=RoomStatus.VACANT,
        created_by=created_by,
        updated_by=created_by,
    )


# ================================================================
# CREATE
# ================================================================

async def create_room(
    request: RoomCreateRequest,
    created_by: str,
) -> RoomResponse:
    """
    Creates a new room.

    Validations:
    - Room number must be unique
    - Monthly rate must be greater than zero
    - Max occupants must be at least 1

    New rooms always start with VACANT status.
    """
    await _assert_no_duplicate_room_number(request.room_number)
    _assert_rate_is_positive(request.monthly_rate)

    room = _build_room_from_request(request, created_by)
    created = await room_repository.create_room(room)
    return RoomResponse.from_room(created)


# ================================================================
# READ
# ================================================================

async def get_all_rooms(
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """Returns a paginated list of all rooms."""
    rooms = await room_repository.get_all_rooms(skip=skip, limit=limit)
    return [RoomResponse.from_room(r) for r in rooms]


async def get_room_by_id(room_id: PydanticObjectId) -> RoomResponse:
    """
    Returns a single room by ID.
    Raises 404 if not found.
    """
    room = await _assert_room_exists(room_id)
    return RoomResponse.from_room(room)


async def get_room_by_number(room_number: str) -> RoomResponse:
    """
    Returns a room by its room number.
    Raises 404 if not found.
    """
    room = await room_repository.get_room_by_number(room_number)
    if not room:
        raise ResourceNotFoundException(
            f"Room number '{room_number}' not found."
        )
    return RoomResponse.from_room(room)


async def get_rooms_by_status(
    status: RoomStatus,
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """Returns rooms filtered by status."""
    rooms = await room_repository.get_rooms_by_status(
        status=status, skip=skip, limit=limit
    )
    return [RoomResponse.from_room(r) for r in rooms]


async def get_rooms_by_type(
    room_type: RoomType,
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """Returns rooms filtered by type."""
    rooms = await room_repository.get_rooms_by_type(
        room_type=room_type, skip=skip, limit=limit
    )
    return [RoomResponse.from_room(r) for r in rooms]


async def get_vacant_rooms(
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """
    Returns all vacant rooms.
    Used by the room selection UI when registering a new tenant.
    """
    rooms = await room_repository.get_vacant_rooms(skip=skip, limit=limit)
    return [RoomResponse.from_room(r) for r in rooms]


async def get_rooms_under_maintenance(
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """
    Returns all rooms currently under maintenance.
    Used by the maintenance dashboard.
    """
    rooms = await room_repository.get_rooms_under_maintenance(
        skip=skip, limit=limit
    )
    return [RoomResponse.from_room(r) for r in rooms]


async def get_rooms_by_rate_range(
    min_rate: float,
    max_rate: float,
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """
    Returns rooms within a monthly rate range.
    Raises 400 if min_rate is greater than max_rate.
    """
    if min_rate > max_rate:
        raise BadRequestException(
            f"min_rate ({min_rate}) cannot be greater than max_rate ({max_rate})."
        )
    if min_rate < 0:
        raise BadRequestException("min_rate cannot be negative.")

    rooms = await room_repository.get_rooms_by_rate_range(
        min_rate=min_rate, max_rate=max_rate, skip=skip, limit=limit
    )
    return [RoomResponse.from_room(r) for r in rooms]


async def search_rooms(
    query: str,
    skip: int = 0,
    limit: int = 20,
) -> list[RoomResponse]:
    """
    Searches rooms by room number or description.
    Raises 400 if query is empty.
    """
    if not query or not query.strip():
        raise BadRequestException("Search query must not be empty.")

    rooms = await room_repository.search_rooms(
        query=query.strip(), skip=skip, limit=limit
    )
    return [RoomResponse.from_room(r) for r in rooms]


async def get_room_stats() -> dict:
    """
    Returns room counts grouped by status.
    Used by DashboardService for the occupancy stats grid.
    """
    total       = await room_repository.count_all_rooms()
    vacant      = await room_repository.count_rooms_by_status(RoomStatus.VACANT)
    occupied    = await room_repository.count_rooms_by_status(RoomStatus.OCCUPIED)
    maintenance = await room_repository.count_rooms_by_status(RoomStatus.MAINTENANCE)
    reserved    = await room_repository.count_rooms_by_status(RoomStatus.RESERVED)

    occupancy_rate = round((occupied / total * 100), 2) if total > 0 else 0.0

    return {
        "total":          total,
        "vacant":         vacant,
        "occupied":       occupied,
        "maintenance":    maintenance,
        "reserved":       reserved,
        "occupancy_rate": f"{occupancy_rate}%",
    }


# ================================================================
# UPDATE
# ================================================================

async def update_room(
    room_id: PydanticObjectId,
    request: RoomUpdateRequest,
    updated_by: str,
) -> RoomResponse:
    """
    Partially updates a room's profile fields.

    Only fields present in the request are updated.
    Room number uniqueness is re-validated if changed.
    Monthly rate is re-validated if changed.
    """
    room = await _assert_room_exists(room_id)

    updates: dict = {}

    if request.room_number is not None and request.room_number != room.room_number:
        await _assert_no_duplicate_room_number(request.room_number, exclude_id=room_id)
        updates["room_number"] = request.room_number

    if request.floor_level   is not None: updates["floor_level"]   = request.floor_level
    if request.room_type     is not None: updates["room_type"]     = request.room_type
    if request.description   is not None: updates["description"]   = request.description
    if request.max_occupants is not None: updates["max_occupants"] = request.max_occupants

    if request.monthly_rate is not None:
        _assert_rate_is_positive(request.monthly_rate)
        updates["monthly_rate"] = request.monthly_rate

    if request.deposit_multiplier is not None:
        if request.deposit_multiplier <= 0:
            raise BadRequestException("deposit_multiplier must be greater than zero.")
        updates["deposit_multiplier"] = request.deposit_multiplier

    if request.advance_multiplier is not None:
        if request.advance_multiplier <= 0:
            raise BadRequestException("advance_multiplier must be greater than zero.")
        updates["advance_multiplier"] = request.advance_multiplier

    if request.dimension is not None:
        updates["dimension"] = RoomDimension(
            length_sqm=request.dimension.length_sqm,
            width_sqm=request.dimension.width_sqm,
        ).model_dump()

    if request.amenities is not None:
        updates["amenities"] = [
            RoomAmenity(
                name=a.name,
                description=a.description,
                is_working=a.is_working,
            ).model_dump()
            for a in request.amenities
        ]

    if not updates:
        raise BadRequestException("No valid fields provided for update.")

    updated = await room_repository.update_room(
        room_id=room_id,
        updates=updates,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


async def update_room_status(
    room_id: PydanticObjectId,
    status: RoomStatus,
    updated_by: str,
) -> RoomResponse:
    """
    Updates room status directly.

    Rules:
    - Cannot manually set OCCUPIED — use LeaseService.create_lease() instead
    - Cannot set VACANT if room still has occupants
    """
    room = await _assert_room_exists(room_id)

    if status == RoomStatus.OCCUPIED:
        raise BadRequestException(
            "Cannot manually set room to OCCUPIED. "
            "Create a lease via LeaseService to occupy a room."
        )

    if status == RoomStatus.VACANT and room.current_occupants > 0:
        raise BadRequestException(
            f"Cannot set room {room.room_number} to VACANT "
            f"while it has {room.current_occupants} active occupant(s). "
            "Terminate the lease first."
        )

    updated = await room_repository.update_room_status(
        room_id=room_id,
        status=status,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


# ================================================================
# MAINTENANCE
# ================================================================

async def set_room_under_maintenance(
    room_id: PydanticObjectId,
    maintenance_notes: str,
    updated_by: str,
) -> RoomResponse:
    """
    Flags a room as under maintenance.

    Validations:
    - Room must exist
    - Room must not be currently OCCUPIED
    - Maintenance notes must not be empty
    """
    room = await _assert_room_exists(room_id)

    if room.is_occupied:
        raise BadRequestException(
            f"Room {room.room_number} is currently occupied. "
            "Cannot start maintenance while a tenant is assigned."
        )

    if not maintenance_notes or not maintenance_notes.strip():
        raise BadRequestException("Maintenance notes must not be empty.")

    updated = await room_repository.set_maintenance(
        room_id=room_id,
        maintenance_notes=maintenance_notes.strip(),
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


async def complete_room_maintenance(
    room_id: PydanticObjectId,
    updated_by: str,
) -> RoomResponse:
    """
    Marks room maintenance as complete and sets status back to VACANT.

    Validations:
    - Room must exist
    - Room must currently be in MAINTENANCE status
    """
    room = await _assert_room_exists(room_id)

    if room.status != RoomStatus.MAINTENANCE:
        raise BadRequestException(
            f"Room {room.room_number} is not currently under maintenance."
        )

    updated = await room_repository.clear_maintenance(
        room_id=room_id,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


# ================================================================
# OCCUPANCY  (called by LeaseService — not from controllers)
# ================================================================

async def occupy_room(
    room_id: PydanticObjectId,
    updated_by: str,
) -> RoomResponse:
    """
    Increments occupant count and sets status to OCCUPIED.
    Called exclusively by LeaseService.create_lease().
    Do NOT call this from a controller directly.

    Validations:
    - Room must exist
    - Room must be VACANT or RESERVED
    - Room must not be at full capacity
    """
    room = await _assert_room_exists(room_id)

    if room.status == RoomStatus.MAINTENANCE:
        raise BadRequestException(
            f"Room {room.room_number} is under maintenance and cannot be occupied."
        )

    if room.status == RoomStatus.OCCUPIED and room.is_full:
        raise BadRequestException(
            f"Room {room.room_number} is already at full capacity "
            f"({room.max_occupants} occupant(s))."
        )

    _assert_occupants_within_capacity(room)

    updated = await room_repository.increment_occupants(
        room_id=room_id,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


async def vacate_room(
    room_id: PydanticObjectId,
    updated_by: str,
) -> RoomResponse:
    """
    Decrements occupant count and sets status to VACANT if empty.
    Called exclusively by LeaseService.terminate_lease().
    Do NOT call this from a controller directly.

    Validations:
    - Room must exist
    - Room must currently be OCCUPIED
    """
    room = await _assert_room_exists(room_id)

    if not room.is_occupied:
        raise BadRequestException(
            f"Room {room.room_number} is not currently occupied."
        )

    updated = await room_repository.decrement_occupants(
        room_id=room_id,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


# ================================================================
# IMAGES
# ================================================================

async def add_room_image(
    room_id: PydanticObjectId,
    image_url: str,
    updated_by: str,
) -> RoomResponse:
    """
    Adds an image URL to the room's image list.
    image_url should come from FileStorageService after upload.

    Validations:
    - Room must exist
    - Image URL must not be empty
    - Same image URL must not already exist in the list
    """
    room = await _assert_room_exists(room_id)

    if not image_url or not image_url.strip():
        raise BadRequestException("Image URL must not be empty.")

    if image_url in room.images:
        raise DuplicateResourceException(
            "This image already exists for this room."
        )

    updated = await room_repository.add_room_image(
        room_id=room_id,
        image_url=image_url.strip(),
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


async def remove_room_image(
    room_id: PydanticObjectId,
    image_url: str,
    updated_by: str,
) -> RoomResponse:
    """
    Removes an image URL from the room's image list.

    Validations:
    - Room must exist
    - Image URL must exist in the room's image list
    """
    room = await _assert_room_exists(room_id)

    if image_url not in room.images:
        raise ResourceNotFoundException(
            "Image not found in this room's image list."
        )

    updated = await room_repository.remove_room_image(
        room_id=room_id,
        image_url=image_url,
        updated_by=updated_by,
    )
    return RoomResponse.from_room(updated)


# ================================================================
# DELETE
# ================================================================

async def delete_room(room_id: PydanticObjectId) -> dict:
    """
    Hard deletes a room record.

    WARNING: Prefer setting status to MAINTENANCE instead.
    Only use for test data cleanup or admin corrections.

    Validations:
    - Room must exist
    - Room must not be currently OCCUPIED
    - Room must have zero current occupants
    """
    room = await _assert_room_exists(room_id)

    if room.is_occupied:
        raise BadRequestException(
            f"Cannot delete room {room.room_number} while it is occupied. "
            "Terminate the lease first."
        )

    if room.current_occupants > 0:
        raise BadRequestException(
            f"Cannot delete room {room.room_number} with "
            f"{room.current_occupants} active occupant(s)."
        )

    deleted = await room_repository.delete_room(room_id)
    if not deleted:
        raise ResourceNotFoundException(f"Room not found: {room_id}")

    return {"message": f"Room {room.room_number} has been permanently deleted."}