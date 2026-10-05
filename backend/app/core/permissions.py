"""Central role -> permission matrix.

Routes declare the permission they need (`require(Permission.X)`); they never
compare role strings. The frontend receives the same permission list from
`/api/me` so UI visibility and backend enforcement share one source of truth.
"""
from enum import StrEnum

from app.core.enums import Role


class Permission(StrEnum):
    # Academic structure
    ACADEMIC_READ = "academic.read"
    ACADEMIC_MANAGE = "academic.manage"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"

    # Teaching plans (master data)
    PLANS_READ_ALL = "plans.read_all"
    PLANS_MANAGE = "plans.manage"
    PLANS_IMPORT = "plans.import"
    PLANS_PUBLISH = "plans.publish"

    # Professor execution
    TASKS_READ_OWN = "tasks.read_own"
    PROGRESS_UPDATE_OWN = "progress.update_own"
    PROGRESS_SUBMIT_OWN = "progress.submit_own"

    # Verification
    VERIFY_CL_CH = "verify.cl_ch"
    VERIFY_OM = "verify.om"
    VERIFICATION_READ = "verification.read"

    # Classroom operations (entry / exit timings)
    OPERATIONS_READ = "operations.read"
    OPERATIONS_RECORD = "operations.record"

    # Monitoring
    REPORTS_READ = "reports.read"
    AUDIT_READ = "audit.read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({
        Permission.ACADEMIC_READ, Permission.ACADEMIC_MANAGE,
        Permission.USERS_READ, Permission.USERS_MANAGE,
        Permission.PLANS_READ_ALL, Permission.PLANS_MANAGE, Permission.PLANS_IMPORT, Permission.PLANS_PUBLISH,
        Permission.VERIFICATION_READ, Permission.REPORTS_READ, Permission.AUDIT_READ,
        Permission.OPERATIONS_READ,
    }),
    Role.PROFESSOR: frozenset({
        Permission.ACADEMIC_READ,
        Permission.TASKS_READ_OWN, Permission.PROGRESS_UPDATE_OWN, Permission.PROGRESS_SUBMIT_OWN,
    }),
    Role.CL_CH: frozenset({
        Permission.ACADEMIC_READ, Permission.PLANS_READ_ALL,
        Permission.VERIFY_CL_CH, Permission.VERIFICATION_READ, Permission.REPORTS_READ,
    }),
    Role.OM: frozenset({
        Permission.ACADEMIC_READ, Permission.PLANS_READ_ALL,
        Permission.OPERATIONS_READ, Permission.OPERATIONS_RECORD,
        Permission.VERIFY_OM, Permission.VERIFICATION_READ, Permission.REPORTS_READ,
    }),
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(Role(role), frozenset())


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in permissions_for(role)
