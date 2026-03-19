
from beanie import PydanticObjectId
from beanie.operators import In, Set
from typing import Optional
from datetime import datetime

from models.tenant import Tenant, TenantStatus



async def get_all_tenants(
    skip: int = 0,
    limit: int = 20,
    fetch_links: bool = False) -> list[Tenant]:
    """
    Returns a paginated list of all tenants.
    Use fetch_links=True to populate room_id and user_id references.
    """
    return await Tenant.find_all(
        fetch_links=fetch_links
    ).skip(skip).limit(limit).to_list()


async def get_tenant_by_id(
    tenant_id: PydanticObjectId,
    fetch_links: bool = False
) -> Optional[Tenant]:
    """
    Returns a single tenant by MongoDB ObjectId.
    Returns None if not found.
    """
    return await Tenant.get(tenant_id, fetch_links=fetch_links)


async def get_tenant_by_user_id(
    user_id: PydanticObjectId,
    fetch_links: bool = False
) -> Optional[Tenant]:
    """
    Returns the tenant profile linked to a specific User account.
    One User → One Tenant profile.
    """
    return await Tenant.find_one(
        Tenant.user_id.id == user_id,
        fetch_links=fetch_links
    )


async def get_tenant_by_email(email: str) -> Optional[Tenant]:
    """
    Looks up a tenant by their contact email.
    Note: This is the tenant's contact email (models/tenant.py),
    not the User login email (models/user.py).
    """
    return await Tenant.find_one(Tenant.email == email)


async def get_tenant_by_phone(phone: str) -> Optional[Tenant]:
    """
    Looks up a tenant by phone number.
    """
    return await Tenant.find_one(Tenant.phone == phone)


async def get_tenants_by_status(
    status: TenantStatus,
    skip: int = 0,
    limit: int = 20
) -> list[Tenant]:
    """
    Returns all tenants filtered by status.
    e.g. get_tenants_by_status(TenantStatus.ACTIVE)
    """
    return await Tenant.find(
        Tenant.status == status
    ).skip(skip).limit(limit).to_list()


async def get_tenant_by_room(
    room_id: PydanticObjectId,
    fetch_links: bool = False
) -> Optional[Tenant]:
    """
    Returns the tenant currently occupying a given room.
    Returns None if the room is vacant.
    """
    return await Tenant.find_one(
        Tenant.room_id.id == room_id,
        Tenant.status == TenantStatus.ACTIVE,
        fetch_links=fetch_links
    )


async def get_tenants_with_outstanding_balance(
    skip: int = 0,
    limit: int = 20
) -> list[Tenant]:
    """
    Returns tenants who have an unpaid balance (outstanding_balance > 0).
    Used by BillingService for payment reminders.
    """
    return await Tenant.find(
        Tenant.outstanding_balance > 0
    ).skip(skip).limit(limit).to_list()


async def get_unverified_tenants(
    skip: int = 0,
    limit: int = 20
) -> list[Tenant]:
    """
    Returns tenants whose government ID has not yet been verified.
    Used by admin/staff for ID review queue.
    """
    return await Tenant.find(
        Tenant.government_id != None,                                   # noqa: E711
        Tenant.government_id.verified == False                          # noqa: E712
    ).skip(skip).limit(limit).to_list()


async def search_tenants(
    query: str,
    skip: int = 0,
    limit: int = 20
) -> list[Tenant]:
    """
    Case-insensitive search across first_name, last_name, email, phone.
    Uses MongoDB regex — add a text index on these fields for large datasets.
    """
    import re
    pattern = re.compile(query, re.IGNORECASE)
    return await Tenant.find(
        {
            "$or": [
                {"first_name":  {"$regex": pattern}},
                {"last_name":   {"$regex": pattern}},
                {"email":       {"$regex": pattern}},
                {"phone":       {"$regex": pattern}},
            ]
        }
    ).skip(skip).limit(limit).to_list()


async def count_tenants_by_status(status: TenantStatus) -> int:
    """
    Returns total count of tenants with the given status.
    Used by DashboardService for occupancy stats.
    """
    return await Tenant.find(Tenant.status == status).count()


async def count_all_tenants() -> int:
    """
    Returns total count of all tenants regardless of status.
    """
    return await Tenant.count()


# ================================================================
# WRITE OPERATIONS
# ================================================================

async def create_tenant(tenant: Tenant) -> Tenant:
    """
    Inserts a new Tenant document into the 'tenants' collection.
    The tenant object should be fully constructed before calling this.

    Example:
        tenant = Tenant(user_id=user.id, first_name="Juan", ...)
        created = await create_tenant(tenant)
    """
    return await tenant.insert()


async def update_tenant(
    tenant_id: PydanticObjectId,
    updates: dict,
    updated_by: str
) -> Optional[Tenant]:
    """
    Partially updates a tenant document using a dict of field changes.
    Automatically stamps updated_at and updated_by.

    Example:
        await update_tenant(
            tenant_id=tenant.id,
            updates={"first_name": "Juan", "phone": "09171234567"},
            updated_by="admin_user"
        )
    """
    tenant = await Tenant.get(tenant_id)
    if not tenant:
        return None

    updates["updated_at"] = datetime.utcnow()
    updates["updated_by"] = updated_by

    await tenant.update(Set(updates))
    return await Tenant.get(tenant_id)


async def update_tenant_status(
    tenant_id: PydanticObjectId,
    status: TenantStatus,
    updated_by: str
) -> Optional[Tenant]:
    """
    Updates only the status field of a tenant.
    Stamps updated_at and updated_by automatically.
    """
    return await update_tenant(
        tenant_id=tenant_id,
        updates={"status": status},
        updated_by=updated_by
    )


async def assign_room(
    tenant_id: PydanticObjectId,
    room_id: PydanticObjectId,
    move_in_date: datetime,
    updated_by: str
) -> Optional[Tenant]:
    """
    Assigns a room to a tenant and records move-in date.
    Also sets status to ACTIVE.
    Called by LeaseService when a new lease is created.
    """
    return await update_tenant(
        tenant_id=tenant_id,
        updates={
            "room_id":      room_id,
            "move_in_date": move_in_date,
            "move_out_date": None,
            "status":       TenantStatus.ACTIVE,
        },
        updated_by=updated_by
    )


async def unassign_room(
    tenant_id: PydanticObjectId,
    move_out_date: datetime,
    updated_by: str
) -> Optional[Tenant]:
    """
    Removes room assignment from a tenant and records move-out date.
    Sets status to MOVED_OUT.
    Called by LeaseService when a lease is terminated.
    """
    return await update_tenant(
        tenant_id=tenant_id,
        updates={
            "room_id":       None,
            "move_out_date": move_out_date,
            "status":        TenantStatus.MOVED_OUT,
        },
        updated_by=updated_by
    )


async def update_balance(
    tenant_id: PydanticObjectId,
    outstanding_balance: float,
    total_paid: float
) -> Optional[Tenant]:
    """
    Updates the tenant's financial summary fields.
    Called exclusively by BillingService and PaymentService.
    Never call this directly from a controller.
    """
    tenant = await Tenant.get(tenant_id)
    if not tenant:
        return None

    await tenant.update(Set({
        "outstanding_balance": outstanding_balance,
        "total_paid":          total_paid,
        "updated_at":          datetime.utcnow(),
    }))
    return await Tenant.get(tenant_id)


async def record_deposit(
    tenant_id: PydanticObjectId,
    amount: float,
    deposit_date: datetime,
    updated_by: str
) -> Optional[Tenant]:
    """
    Marks the security deposit as paid and records amount + date.
    Called by PaymentService when a deposit payment is confirmed.
    """
    return await update_tenant(
        tenant_id=tenant_id,
        updates={
            "deposit_paid":   True,
            "deposit_amount": amount,
            "deposit_date":   deposit_date,
        },
        updated_by=updated_by
    )


async def verify_government_id(
    tenant_id: PydanticObjectId,
    verified_by: str
) -> Optional[Tenant]:
    """
    Marks the tenant's government ID as verified.
    Records who verified it and when.
    Called by admin/staff after manual document review.
    """
    tenant = await Tenant.get(tenant_id)
    if not tenant or not tenant.government_id:
        return None

    await tenant.update(Set({
        "government_id.verified":    True,
        "government_id.verified_by": verified_by,
        "government_id.verified_at": datetime.utcnow(),
        "updated_at":                datetime.utcnow(),
        "updated_by":                verified_by,
    }))
    return await Tenant.get(tenant_id)


async def update_profile_picture(
    tenant_id: PydanticObjectId,
    filepath_or_url: str,
    updated_by: str
) -> Optional[Tenant]:
    """
    Updates the tenant's profile picture path or URL.
    Called by FileStorageService after a successful upload.
    """
    return await update_tenant(
        tenant_id=tenant_id,
        updates={"profile_picture": filepath_or_url},
        updated_by=updated_by
    )


async def delete_tenant(tenant_id: PydanticObjectId) -> bool:
    """
    Hard deletes a tenant document from MongoDB.
    WARNING: Prefer update_tenant_status(INACTIVE / MOVED_OUT) instead.
    Only use this for test cleanup or admin data correction.

    Returns True if deleted, False if tenant was not found.
    """
    tenant = await Tenant.get(tenant_id)
    if not tenant:
        return False
    await tenant.delete()
    return True