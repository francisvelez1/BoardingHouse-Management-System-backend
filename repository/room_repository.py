# ============================================================
# repository/room_repository.py
# ResidEase – Boarding House Management System
# ============================================================

from beanie import PydanticObjectId
from beanie.operators import Set
from typing import Optional
from datetime import datetime

from models.room import Room, RoomStatus, RoomType


# ================================================================
# READ OPERATIONS
# ================================================================

async def get_all_rooms(
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns a paginated list of all rooms.
    """
    return await Room.find_all().skip(skip).limit(limit).to_list()


async def get_room_by_id(
    room_id: PydanticObjectId,
) -> Optional[Room]:
    """
    Returns a single room by MongoDB ObjectId.
    Returns None if not found.
    """
    return await Room.get(room_id)


async def get_room_by_number(room_number: str) -> Optional[Room]:
    """
    Returns a room by its room number.
    e.g. get_room_by_number("101")
    """
    return await Room.find_one(Room.room_number == room_number)


async def get_rooms_by_status(
    status: RoomStatus,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns all rooms filtered by status.
    e.g. get_rooms_by_status(RoomStatus.VACANT)
    """
    return await Room.find(
        Room.status == status
    ).skip(skip).limit(limit).to_list()


async def get_rooms_by_type(
    room_type: RoomType,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns all rooms filtered by type.
    e.g. get_rooms_by_type(RoomType.SINGLE)
    """
    return await Room.find(
        Room.room_type == room_type
    ).skip(skip).limit(limit).to_list()


async def get_vacant_rooms(
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns all rooms with VACANT status.
    Used by frontend room selection when assigning a tenant.
    """
    return await Room.find(
        Room.status == RoomStatus.VACANT
    ).skip(skip).limit(limit).to_list()


async def get_rooms_by_rate_range(
    min_rate: float,
    max_rate: float,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns rooms within a monthly rate range.
    Used for tenant room search / filtering.
    """
    return await Room.find(
        Room.monthly_rate >= min_rate,
        Room.monthly_rate <= max_rate,
    ).skip(skip).limit(limit).to_list()


async def get_rooms_under_maintenance(
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Returns all rooms currently under maintenance.
    Used by maintenance dashboard.
    """
    return await Room.find(
        Room.status == RoomStatus.MAINTENANCE
    ).skip(skip).limit(limit).to_list()


async def search_rooms(
    query: str,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """
    Case-insensitive search across room_number and description.
    """
    import re
    pattern = re.compile(query, re.IGNORECASE)
    return await Room.find(
        {
            "$or": [
                {"room_number": {"$regex": pattern}},
                {"description": {"$regex": pattern}},
            ]
        }
    ).skip(skip).limit(limit).to_list()


async def exists_by_room_number(room_number: str) -> bool:
    """
    Returns True if a room with the given number already exists.
    Used for duplicate check on room creation.
    """
    return await Room.find_one(Room.room_number == room_number) is not None


async def count_all_rooms() -> int:
    """Returns total count of all rooms."""
    return await Room.count()


async def count_rooms_by_status(status: RoomStatus) -> int:
    """
    Returns count of rooms with the given status.
    Used by DashboardService for occupancy stats.
    """
    return await Room.find(Room.status == status).count()


# ================================================================
# WRITE OPERATIONS
# ================================================================

async def create_room(room: Room) -> Room:
    """
    Inserts a new Room document into the 'rooms' collection.
    The room object should be fully constructed before calling this.

    Example:
        room = Room(room_number="101", room_type=RoomType.SINGLE, monthly_rate=5000)
        created = await create_room(room)
    """
    return await room.insert()


async def update_room(
    room_id: PydanticObjectId,
    updates: dict,
    updated_by: str,
) -> Optional[Room]:
    """
    Partially updates a room document using a dict of field changes.
    Automatically stamps updated_at and updated_by.

    Example:
        await update_room(
            room_id=room.id,
            updates={"monthly_rate": 6000, "description": "Newly renovated"},
            updated_by="admin_user"
        )
    """
    room = await Room.get(room_id)
    if not room:
        return None

    updates["updated_at"] = datetime.utcnow()
    updates["updated_by"] = updated_by

    await room.update(Set(updates))
    return await Room.get(room_id)


async def update_room_status(
    room_id: PydanticObjectId,
    status: RoomStatus,
    updated_by: str,
) -> Optional[Room]:
    """
    Updates only the status field of a room.
    Called by LeaseService on move-in / move-out.
    Called by MaintenanceService when maintenance starts / ends.
    """
    return await update_room(
        room_id=room_id,
        updates={"status": status},
        updated_by=updated_by,
    )


async def increment_occupants(
    room_id: PydanticObjectId,
    updated_by: str,
) -> Optional[Room]:
    """
    Increments current_occupants by 1 and sets status to OCCUPIED.
    Called by LeaseService when a new lease is activated.
    """
    room = await Room.get(room_id)
    if not room:
        return None

    new_count = room.current_occupants + 1
    new_status = RoomStatus.OCCUPIED if new_count >= 1 else RoomStatus.VACANT

    return await update_room(
        room_id=room_id,
        updates={
            "current_occupants": new_count,
            "status":            new_status,
        },
        updated_by=updated_by,
    )


async def decrement_occupants(
    room_id: PydanticObjectId,
    updated_by: str,
) -> Optional[Room]:
    """
    Decrements current_occupants by 1.
    Sets status to VACANT if count reaches 0.
    Called by LeaseService when a lease is terminated.
    """
    room = await Room.get(room_id)
    if not room:
        return None

    new_count  = max(0, room.current_occupants - 1)
    new_status = RoomStatus.VACANT if new_count == 0 else RoomStatus.OCCUPIED

    return await update_room(
        room_id=room_id,
        updates={
            "current_occupants": new_count,
            "status":            new_status,
        },
        updated_by=updated_by,
    )


async def set_maintenance(
    room_id: PydanticObjectId,
    maintenance_notes: str,
    updated_by: str,
) -> Optional[Room]:
    """
    Sets room status to MAINTENANCE and records notes and date.
    Called by MaintenanceService when a work order is started.
    """
    return await update_room(
        room_id=room_id,
        updates={
            "status":                RoomStatus.MAINTENANCE,
            "maintenance_notes":     maintenance_notes,
            "last_maintenance_date": datetime.utcnow(),
        },
        updated_by=updated_by,
    )


async def clear_maintenance(
    room_id: PydanticObjectId,
    updated_by: str,
) -> Optional[Room]:
    """
    Clears maintenance status and sets room back to VACANT.
    Called by MaintenanceService when a work order is completed.
    """
    return await update_room(
        room_id=room_id,
        updates={
            "status":            RoomStatus.VACANT,
            "maintenance_notes": None,
        },
        updated_by=updated_by,
    )


async def add_room_image(
    room_id: PydanticObjectId,
    image_url: str,
    updated_by: str,
) -> Optional[Room]:
    """
    Appends a new image URL to the room's images list.
    Called by FileStorageService after a successful upload.
    """
    room = await Room.get(room_id)
    if not room:
        return None

    updated_images = room.images + [image_url]
    return await update_room(
        room_id=room_id,
        updates={"images": updated_images},
        updated_by=updated_by,
    )


async def remove_room_image(
    room_id: PydanticObjectId,
    image_url: str,
    updated_by: str,
) -> Optional[Room]:
    """
    Removes a specific image URL from the room's images list.
    Called by FileStorageService after a successful deletion.
    """
    room = await Room.get(room_id)
    if not room:
        return None

    updated_images = [img for img in room.images if img != image_url]
    return await update_room(
        room_id=room_id,
        updates={"images": updated_images},
        updated_by=updated_by,
    )


async def delete_room(room_id: PydanticObjectId) -> bool:
    """
    Hard deletes a room document from MongoDB.
    WARNING: Prefer update_room_status(MAINTENANCE) instead.
    Only use this for test cleanup or admin data correction.
    Never delete a room that has active tenants or lease history.

    Returns True if deleted, False if room was not found.
    """
    room = await Room.get(room_id)
    if not room:
        return False
    await room.delete()
    return True