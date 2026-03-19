

from beanie import PydanticObjectId
from beanie.operators import Set
from typing import Optional
from datetime import datetime

from models.user import User, RoleName
from models.role import (
    get_role_level,
    is_manager_or_above,
    ROLE_PERMISSIONS,
    ROLE_DISPLAY_NAMES,
)


# ================================================================
# READ — role-focused user queries
# ================================================================

async def get_users_by_role(role: RoleName) -> list[User]:
    """
    Returns all users assigned to a specific role.

    Example:
        await get_users_by_role(RoleName.TENANT)
        → [User, User, ...]
    """
    return await User.find(User.role == role).to_list()


async def get_users_by_roles(roles: list[RoleName]) -> list[User]:
    """
    Returns all users whose role is in the provided list.

    Example:
        await get_users_by_roles([RoleName.ADMIN, RoleName.MANAGER])
    """
    return await User.find(
        {"role": {"$in": [r.value for r in roles]}}
    ).to_list()


async def get_staff_and_above() -> list[User]:
    """
    Returns all users with STAFF, MANAGER, or ADMIN role.
    Used by admin user management to list internal staff.
    """
    staff_roles = [
        role for role in RoleName
        if get_role_level(role) >= get_role_level(RoleName.STAFF)
    ]
    return await get_users_by_roles(staff_roles)


async def get_managers_and_above() -> list[User]:
    """
    Returns all users with MANAGER or ADMIN role.
    Used for escalation and approval workflows.
    """
    manager_roles = [
        role for role in RoleName
        if is_manager_or_above(role)
    ]
    return await get_users_by_roles(manager_roles)


async def get_role_of_user(user_id: PydanticObjectId) -> Optional[RoleName]:
    """
    Returns the role of a specific user by ID.
    Returns None if user does not exist.

    Example:
        role = await get_role_of_user(user.id)
        → RoleName.TENANT
    """
    user = await User.get(user_id)
    return user.role if user else None


async def count_users_by_role(role: RoleName) -> int:
    """
    Returns the count of users assigned to a specific role.
    Used by DashboardService for staff stats.

    Example:
        await count_users_by_role(RoleName.TENANT) → 42
    """
    return await User.find(User.role == role).count()


async def count_all_roles() -> dict[str, int]:
    """
    Returns a count of users grouped by every role.
    Used by DashboardService and admin overview.

    Returns:
        {
            "ROLE_ADMIN":       1,
            "ROLE_MANAGER":     2,
            "ROLE_STAFF":       3,
            "ROLE_MAINTENANCE": 1,
            "ROLE_TENANT":      42,
        }
    """
    return {
        role.value: await User.find(User.role == role).count()
        for role in RoleName
    }


async def user_has_permission(
    user_id: PydanticObjectId,
    permission: str,
) -> bool:
    """
    Returns True if the user's role includes the given permission.
    Fetches the user, resolves their role, checks ROLE_PERMISSIONS.

    Example:
        await user_has_permission(user.id, "tenant:delete") → False
    """
    role = await get_role_of_user(user_id)
    if not role:
        return False
    return permission in ROLE_PERMISSIONS.get(role, [])


# ================================================================
# WRITE — role assignment on User documents
# ================================================================

async def assign_role(
    user_id:    PydanticObjectId,
    new_role:   RoleName,
    updated_by: str,
) -> Optional[User]:
    """
    Assigns a new role to an existing user.
    Stamps updated_at and updated_by automatically.

    Rules enforced by RoleService (not here):
    - Cannot assign ADMIN role unless caller is ADMIN
    - Cannot downgrade a user with higher authority than the caller

    Example:
        await assign_role(user.id, RoleName.MANAGER, "admin_user")
    """
    user = await User.get(user_id)
    if not user:
        return None

    await user.update(Set({
        "role":       new_role,
        "updated_at": datetime.utcnow(),
        "updated_by": updated_by,
    }))
    return await User.get(user_id)


async def bulk_assign_role(
    user_ids:   list[PydanticObjectId],
    new_role:   RoleName,
    updated_by: str,
) -> int:
    """
    Assigns the same role to multiple users at once.
    Returns the count of successfully updated users.
    Used by admin bulk operations.

    Example:
        count = await bulk_assign_role(
            [id1, id2, id3],
            RoleName.STAFF,
            "admin_user"
        )
        → 3
    """
    updated_count = 0
    for user_id in user_ids:
        result = await assign_role(user_id, new_role, updated_by)
        if result:
            updated_count += 1
    return updated_count


async def revoke_role_to_default(
    user_id:    PydanticObjectId,
    updated_by: str,
) -> Optional[User]:
    """
    Resets a user's role back to the default TENANT role.
    Used when staff leave or a role needs to be removed.

    Example:
        await revoke_role_to_default(user.id, "admin_user")
    """
    return await assign_role(
        user_id=user_id,
        new_role=RoleName.TENANT,
        updated_by=updated_by,
    )


# ================================================================
# META — role definitions (no DB calls)
# ================================================================

def get_all_role_definitions() -> list[dict]:
    """
    Returns all role definitions as a structured list.
    No database call — purely from role.py constants.
    Used by the admin UI to populate role dropdowns
    and display permission tables.

    Returns:
        [
            {
                "role":         "ROLE_ADMIN",
                "display_name": "Administrator",
                "permissions":  ["tenant:read", "tenant:write", ...]
            },
            ...
        ]
    """
    return [
        {
            "role":         role.value,
            "display_name": ROLE_DISPLAY_NAMES.get(role, role.value),
            "permissions":  ROLE_PERMISSIONS.get(role, []),
        }
        for role in RoleName
    ]