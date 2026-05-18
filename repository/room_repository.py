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
# OWNERSHIP HELPERS
# ================================================================
#
# These helpers build MongoDB query fragments that match only the rooms
# owned by a particular manager. Used by the manager-facing endpoints
# so that Manager B never sees rooms created by Manager A.
#
# See `_owner_clause` below for the full ownership rules — it covers
# both the new `manager_id` column and several legacy `created_by`
# shapes (ObjectId-string and plain username) so existing rooms become
# visible to their original manager without any database migration.

async def _owner_clause(manager_id: PydanticObjectId) -> dict:
    """
    Returns a Mongo `$or` fragment that matches rooms owned by `manager_id`.

    There are three historical shapes of `created_by` in the database:

      1. Rooms created via the manager API (old code path) stored
         ``str(current_user.id)`` — an ObjectId hex string.
      2. Rooms created via the global /api/rooms endpoint stored
         ``current_user.username`` — a plain string like "Emac599".
      3. Rooms created after the migration carry ``manager_id`` directly
         on the document (the cleanest case).

    To make all three cases visible to the right manager *without* a
    one-shot database migration, we resolve the manager's username once
    and include both their ObjectId-hex AND their username in the
    legacy `created_by` match set.
    """
    from models.user import User
    legacy_keys: list[str] = [str(manager_id)]
    user = await User.get(manager_id)
    if user and user.username:
        legacy_keys.append(user.username)

    return {
        "$or": [
            {"manager_id": manager_id},
            {"manager_id": None, "created_by": {"$in": legacy_keys}},
        ]
    }


def _combine(*clauses: dict) -> dict:
    """Combines multiple dict-queries with `$and`. Drops empty clauses."""
    real = [c for c in clauses if c]
    if not real:
        return {}
    if len(real) == 1:
        return real[0]
    return {"$and": real}


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


async def get_rooms_by_manager(
    manager_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 20,
    status: Optional[RoomStatus] = None,
) -> list[Room]:
    """
    Returns rooms owned by the given manager, optionally filtered by status.
    Used by the manager dashboard so Manager B does not see Manager A's rooms.
    """
    status_clause = {"status": status.value} if status else {}
    owner = await _owner_clause(manager_id)
    query = _combine(owner, status_clause)
    return await Room.find(query).skip(skip).limit(limit).to_list()


async def count_rooms_by_manager(
    manager_id: PydanticObjectId,
    status: Optional[RoomStatus] = None,
) -> int:
    """Counts rooms owned by the given manager (optionally filtered by status)."""
    status_clause = {"status": status.value} if status else {}
    owner = await _owner_clause(manager_id)
    query = _combine(owner, status_clause)
    return await Room.find(query).count()


async def get_vacant_rooms_by_manager(
    manager_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """Returns the manager's vacant rooms — used by tenant-assignment UIs."""
    return await get_rooms_by_manager(
        manager_id=manager_id, skip=skip, limit=limit, status=RoomStatus.VACANT,
    )


async def get_rooms_under_maintenance_by_manager(
    manager_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """Returns the manager's rooms currently under maintenance."""
    return await get_rooms_by_manager(
        manager_id=manager_id, skip=skip, limit=limit, status=RoomStatus.MAINTENANCE,
    )


async def search_rooms_by_manager(
    manager_id: PydanticObjectId,
    query: str,
    skip: int = 0,
    limit: int = 20,
) -> list[Room]:
    """Case-insensitive search across room_number/description, scoped to the manager."""
    import re
    pattern = re.compile(query, re.IGNORECASE)
    search_clause = {
        "$or": [
            {"room_number": {"$regex": pattern}},
            {"description": {"$regex": pattern}},
        ]
    }
    owner = await _owner_clause(manager_id)
    return await Room.find(
        _combine(owner, search_clause)
    ).skip(skip).limit(limit).to_list()


async def get_room_by_number_for_manager(
    manager_id: PydanticObjectId,
    room_number: str,
) -> Optional[Room]:
    """
    Returns a room with the given number that the given manager owns.
    Used to enforce per-manager (not global) room-number uniqueness.
    """
    owner = await _owner_clause(manager_id)
    return await Room.find_one(
        _combine(owner, {"room_number": room_number})
    )


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