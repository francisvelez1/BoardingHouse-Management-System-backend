
from enum import Enum
from models.user import RoleName


# ================================================================
# ROLE HIERARCHY
# Defines the authority level of each role.
# Higher number = more authority.
# ================================================================

ROLE_HIERARCHY: dict[RoleName, int] = {
    RoleName.TENANT:      1,
    RoleName.MAINTENANCE: 2,
    RoleName.STAFF:       3,
    RoleName.MANAGER:     4,
    RoleName.ADMIN:       5,
}


# ================================================================
# ROLE PERMISSIONS
# Maps each role to the set of actions it is allowed to perform.
# Used for documentation and future dynamic permission checks.
# ================================================================

ROLE_PERMISSIONS: dict[RoleName, list[str]] = {
    RoleName.ADMIN: [
        "tenant:read",   "tenant:write",   "tenant:delete",
        "room:read",     "room:write",     "room:delete",
        "lease:read",    "lease:write",    "lease:delete",
        "payment:read",  "payment:write",  "payment:delete",
        "user:read",     "user:write",     "user:delete",
        "report:read",   "report:export",
        "dashboard:read",
        "maintenance:read", "maintenance:write",
        "message:read",     "message:write",
        "notification:read",
    ],
    RoleName.MANAGER: [
        "tenant:read",   "tenant:write",
        "room:read",     "room:write",
        "lease:read",    "lease:write",
        "payment:read",  "payment:write",
        "user:read",
        "report:read",   "report:export",
        "dashboard:read",
        "maintenance:read", "maintenance:write",
        "message:read",     "message:write",
        "notification:read",
    ],
    RoleName.STAFF: [
        "tenant:read",
        "room:read",
        "lease:read",
        "payment:read",
        "dashboard:read",
        "maintenance:read",
        "message:read",
        "notification:read",
    ],
    RoleName.MAINTENANCE: [
        "room:read",
        "maintenance:read", "maintenance:write",
        "message:read",
        "notification:read",
    ],
    RoleName.TENANT: [
        "room:read",
        "lease:read",
        "payment:read",
        "maintenance:read", "maintenance:write",
        "message:read",     "message:write",
        "notification:read",
    ],
}


# ================================================================
# ROLE DISPLAY NAMES
# Human-readable names for the frontend UI.
# ================================================================

ROLE_DISPLAY_NAMES: dict[RoleName, str] = {
    RoleName.ADMIN:       "Administrator",
    RoleName.MANAGER:     "Property Manager",
    RoleName.STAFF:       "Staff",
    RoleName.MAINTENANCE: "Maintenance Personnel",
    RoleName.TENANT:      "Tenant",
}


# ================================================================
# ROLE HELPERS
# ================================================================

def get_role_level(role: RoleName) -> int:
    """
    Returns the authority level of a role.
    Higher = more authority.

    Example:
        get_role_level(RoleName.ADMIN)    → 5
        get_role_level(RoleName.TENANT)   → 1
    """
    return ROLE_HIERARCHY.get(role, 0)


def has_permission(role: RoleName, permission: str) -> bool:
    """
    Returns True if the given role has the specified permission.

    Example:
        has_permission(RoleName.ADMIN,  "tenant:delete")  → True
        has_permission(RoleName.TENANT, "tenant:delete")  → False
    """
    return permission in ROLE_PERMISSIONS.get(role, [])


def is_higher_role(role_a: RoleName, role_b: RoleName) -> bool:
    """
    Returns True if role_a has higher authority than role_b.

    Example:
        is_higher_role(RoleName.ADMIN,   RoleName.STAFF)   → True
        is_higher_role(RoleName.TENANT,  RoleName.MANAGER) → False
    """
    return get_role_level(role_a) > get_role_level(role_b)


def is_staff_or_above(role: RoleName) -> bool:
    """
    Returns True if the role is STAFF, MANAGER, or ADMIN.
    Used to guard internal staff-only endpoints.
    """
    return get_role_level(role) >= get_role_level(RoleName.STAFF)


def is_manager_or_above(role: RoleName) -> bool:
    """
    Returns True if the role is MANAGER or ADMIN.
    Used to guard management-level endpoints.
    """
    return get_role_level(role) >= get_role_level(RoleName.MANAGER)


def get_permissions(role: RoleName) -> list[str]:
    """
    Returns the full list of permissions for a given role.

    Example:
        get_permissions(RoleName.TENANT)
        → ["room:read", "lease:read", "payment:read", ...]
    """
    return ROLE_PERMISSIONS.get(role, [])


def get_display_name(role: RoleName) -> str:
    """
    Returns the human-readable display name for a role.

    Example:
        get_display_name(RoleName.MAINTENANCE) → "Maintenance Personnel"
    """
    return ROLE_DISPLAY_NAMES.get(role, role.value)


def get_all_roles() -> list[dict]:
    """
    Returns a list of all roles with their display name,
    level, and permissions.
    Used by the admin user management UI to populate role dropdowns.
    """
    return [
        {
            "role":         role.value,
            "display_name": get_display_name(role),
            "level":        get_role_level(role),
            "permissions":  get_permissions(role),
        }
        for role in RoleName
    ]