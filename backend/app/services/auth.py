from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any

from app.models.auth import (
    ALL_ACTIONS,
    CREATABLE_TENANT_KINDS,
    DEFAULT_TENANT_ID,
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    ROLES,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    SCOPES,
    TENANT_KIND_PERSONAL,
    TENANT_KIND_SYSTEM,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    USER_STATUS_PENDING,
    USER_STATUS_REJECTED,
    USER_STATUSES,
    AuthContext,
    SeriesGrant,
    PieceGrant,
    Membership,
    Role,
    Tenant,
    User,
)
from app.ports.auth_repository import AuthRepository
from app.services.errors import (
    AccountNotActiveError,
    AuthRequiredError,
    BuiltinRoleError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    MembershipNotFoundError,
    PermissionDeniedError,
    RoleInUseError,
    RoleNotFoundError,
    TenantKindError,
    TenantNotFoundError,
    TenantSystemError,
)

PBKDF2_ITERATIONS = 100_000
HASH_ALGORITHM = "sha256"
TOKEN_TTL_SECONDS = 7 * 24 * 3600
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

BUILTIN_ROLES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "owner": ("Owner", ALL_ACTIONS, SCOPE_ALL),
    "admin": (
        "Admin",
        ("read", "write", "review", "manage_members", "manage_quota"),
        SCOPE_ALL,
    ),
    "editor": ("Editor", ("read", "write", "review"), SCOPE_ALL),
    "viewer": ("Viewer", ("read",), SCOPE_ALL),
}
ACTION_SETS: dict[str, set[str]] = {
    key: set(value[1]) for key, value in BUILTIN_ROLES.items()
}
ROLE_RANK = {"owner": 3, "admin": 2, "editor": 1, "viewer": 0}


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        expected = _b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM, password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(digest, expected)


def issue_token(user_id: str, secret: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + int(ttl_seconds)}
    segment = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        secret.encode("utf-8"), segment.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{segment}.{_b64encode(signature)}"


def parse_token(token: str, secret: str) -> str | None:
    if not token or "." not in token:
        return None
    segment, _, signature = token.partition(".")
    expected = hmac.new(
        secret.encode("utf-8"), segment.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        provided = _b64decode(signature)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(provided, expected):
        return None
    try:
        payload = json.loads(_b64decode(segment).decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None


def normalize_role(role: str, default: str = "viewer") -> str:
    value = (role or "").strip().lower()
    return value or default


def actions_for(role: str) -> set[str]:
    key = normalize_role(role)
    if key in ACTION_SETS:
        return set(ACTION_SETS[key])
    return set(ACTION_SETS["viewer"])


def normalize_actions(actions: list[str] | tuple[str, ...] | None) -> list[str]:
    if not actions:
        return []
    allowed = set(ALL_ACTIONS)
    seen: list[str] = []
    for item in actions:
        value = str(item or "").strip().lower()
        if value in allowed and value not in seen:
            seen.append(value)
    return sorted(seen)


def normalize_scope(scope: str | None) -> str:
    value = (scope or SCOPE_ALL).strip().lower()
    return value if value in SCOPES else SCOPE_ALL


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        secret: str = "",
        ttl_seconds: int = TOKEN_TTL_SECONDS,
        mode: str = "disabled",
        require_approval: bool = True,
    ) -> None:
        self.repository = repository
        self.secret = secret or "opencgp-dev-secret"
        self.ttl_seconds = ttl_seconds
        self.mode = (mode or "disabled").strip().lower()
        self.require_approval = bool(require_approval)
        self._seeded = False

    def ensure_default(self) -> None:
        if self._seeded:
            return
        repository = self.repository
        repository.ensure_schema()
        if repository.get_tenant(DEFAULT_TENANT_ID) is None:
            system = repository.create_tenant(
                "Default space", "default", "free", tenant_id=DEFAULT_TENANT_ID
            )
            repository.update_tenant(system.id, kind=TENANT_KIND_SYSTEM)
        else:
            current = repository.get_tenant(DEFAULT_TENANT_ID)
            if current is not None and current.kind != TENANT_KIND_SYSTEM:
                repository.update_tenant(DEFAULT_TENANT_ID, kind=TENANT_KIND_SYSTEM)
        if repository.get_user(DEFAULT_USER_ID) is None:
            repository.create_user(
                DEFAULT_USER_EMAIL,
                hash_password(secrets.token_hex(16)),
                "Local user",
                user_id=DEFAULT_USER_ID,
            )
        if repository.get_membership(DEFAULT_TENANT_ID, DEFAULT_USER_ID) is None:
            repository.add_membership(DEFAULT_TENANT_ID, DEFAULT_USER_ID, "owner")
        self.ensure_tenant_roles(DEFAULT_TENANT_ID)
        self._seeded = True

    def ensure_tenant_roles(self, tenant_id: str) -> list[Role]:
        self.repository.ensure_schema()
        existing = {role.key: role for role in self.repository.list_roles(tenant_id)}
        for key, (name, actions, scope) in BUILTIN_ROLES.items():
            current = existing.get(key)
            if current is None:
                self.repository.create_role(
                    tenant_id, key, name, actions, scope, builtin=True
                )
                continue
            if current.builtin and set(current.actions) != set(actions):
                self.repository.update_role(
                    current.id, name=current.name or name, actions=actions
                )
        return self.repository.list_roles(tenant_id)

    def role_for(self, tenant_id: str, role_key: str) -> Role:
        key = normalize_role(role_key, "viewer")
        role = self.repository.get_role(tenant_id, key)
        if role is None:
            self.ensure_tenant_roles(tenant_id)
            role = self.repository.get_role(tenant_id, key)
        if role is None:
            name, actions, scope = BUILTIN_ROLES["viewer"]
            role = Role(
                id="",
                tenant_id=tenant_id,
                key="viewer",
                name=name,
                actions=list(actions),
                scope=scope,
                builtin=True,
            )
        return role

    def context_for(self, user: User, tenant: Tenant, role_key: str) -> AuthContext:
        role = self.role_for(tenant.id, role_key)
        return AuthContext(
            user=user,
            tenant=tenant,
            role=role.key,
            role_key=role.key,
            role_name=role.name or role.key,
            actions=set(role.actions),
            scope=role.scope or SCOPE_ALL,
        )

    def local_context(self) -> AuthContext:
        self.ensure_default()
        user = self.repository.get_user(DEFAULT_USER_ID)
        tenant = self.repository.get_tenant(DEFAULT_TENANT_ID)
        if user is None or tenant is None:
            raise AuthRequiredError("local identity initialization failed")
        return self.context_for(user, tenant, "owner")

    def register(
        self, email: str, password: str, display_name: str = ""
    ) -> tuple[User, str]:
        self.ensure_default()
        address = (email or "").strip().lower()
        if not EMAIL_PATTERN.match(address):
            raise ValueError("invalid email format")
        if len(password or "") < 8:
            raise ValueError("password must be at least 8 characters")
        if self.repository.get_user_by_email(address) is not None:
            raise EmailAlreadyRegisteredError("this email is already registered")
        bootstrap = self.is_bootstrap_registration()
        auto_active = (
            bootstrap or self.mode != "required" or not self.require_approval
        )
        status = USER_STATUS_ACTIVE if auto_active else USER_STATUS_PENDING
        user = self.repository.create_user(
            address, hash_password(password), display_name, status=status
        )
        label = (display_name or address.split("@")[0]).strip() or address
        tenant = self.repository.create_tenant(
            f"{label}'s space",
            self._unique_slug(label),
            kind=TENANT_KIND_PERSONAL,
            owner_user_id=user.id,
        )
        self.repository.add_membership(tenant.id, user.id, "owner")
        self.ensure_tenant_roles(tenant.id)
        if auto_active:
            self.ensure_system_membership(user.id)
            token = issue_token(user.id, self.secret, self.ttl_seconds)
            return user, token
        return user, ""

    def is_bootstrap_registration(self) -> bool:
        return self.repository.count_users((DEFAULT_USER_ID,)) == 0

    def ensure_system_membership(self, user_id: str) -> Membership | None:
        self.ensure_default()
        existing = self.repository.get_membership(DEFAULT_TENANT_ID, user_id)
        if existing is not None:
            return existing
        return self.repository.add_membership(DEFAULT_TENANT_ID, user_id, "viewer")

    def login(self, email: str, password: str) -> tuple[User, str]:
        self.ensure_default()
        address = (email or "").strip().lower()
        user = self.repository.get_user_by_email(address)
        if user is None and hasattr(self.repository, "get_user_by_email_any"):
            user = self.repository.get_user_by_email_any(address)
        if user is None:
            raise InvalidCredentialsError("incorrect email or password")
        stored = self.repository.get_password_hash(user.id)
        if not verify_password(password, stored):
            raise InvalidCredentialsError("incorrect email or password")
        self.assert_active(user)
        self.repository.touch_login(user.id)
        refreshed = self.repository.get_user(user.id) or user
        return refreshed, issue_token(user.id, self.secret, self.ttl_seconds)

    def assert_active(self, user: User) -> None:
        if user.status == USER_STATUS_PENDING:
            raise AccountNotActiveError("account is pending admin approval")
        if user.status == USER_STATUS_REJECTED:
            raise AccountNotActiveError("account approval was rejected")
        if user.status == USER_STATUS_DISABLED or float(user.deleted_at or 0) > 0:
            raise AccountNotActiveError("account is disabled")

    def resolve(self, token: str, tenant_id: str | None = None) -> AuthContext:
        self.ensure_default()
        user_id = parse_token(token or "", self.secret)
        if not user_id:
            raise AuthRequiredError("access token is invalid or expired")
        user = self.repository.get_user(user_id)
        if user is None:
            raise AuthRequiredError("the user for this access token does not exist")
        self.assert_active(user)
        memberships = self.repository.list_memberships(user.id)
        if not memberships:
            raise MembershipNotFoundError("the current user does not belong to any tenant")
        target = (tenant_id or "").strip()
        if target:
            membership = next(
                (item for item in memberships if item.tenant_id == target), None
            )
            if membership is None:
                raise MembershipNotFoundError("the current user does not belong to this tenant")
        else:
            membership = memberships[0]
        tenant = self.repository.get_tenant(membership.tenant_id)
        if tenant is None:
            raise TenantNotFoundError("tenant not found")
        return self.context_for(user, tenant, membership.role)

    def update_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> User:
        user = self.repository.get_user(user_id)
        if user is None:
            raise AuthRequiredError("user not found")
        next_email = None
        if email is not None:
            address = email.strip().lower()
            if not EMAIL_PATTERN.match(address):
                raise ValueError("invalid email format")
            if address != user.email:
                if self.repository.get_user_by_email(address) is not None:
                    raise EmailAlreadyRegisteredError("this email is already taken")
            next_email = address
        next_name = None
        if display_name is not None:
            label = display_name.strip()
            if not label:
                raise ValueError("display name must not be empty")
            next_name = label
        updated = self.repository.update_user(
            user_id, display_name=next_name, email=next_email
        )
        if updated is None:
            raise AuthRequiredError("user not found")
        return updated

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        stored = self.repository.get_password_hash(user_id)
        if not verify_password(current_password or "", stored):
            raise InvalidCredentialsError("current password is incorrect")
        if len(new_password or "") < 8:
            raise ValueError("new password must be at least 8 characters")
        self.repository.update_password_hash(user_id, hash_password(new_password))

    def set_avatar_key(self, user_id: str, key: str) -> User:
        updated = self.repository.update_user(user_id, avatar_key=key)
        if updated is None:
            raise AuthRequiredError("user not found")
        return updated

    def get_user(self, user_id: str) -> User | None:
        self.ensure_default()
        return self.repository.get_user(user_id)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        self.ensure_default()
        return self.repository.get_tenant(tenant_id)

    def list_users(
        self,
        status: str = "",
        limit: int = 50,
        q: str = "",
        include_deleted: bool = False,
    ) -> list[User]:
        self.ensure_default()
        wanted = (status or "").strip().lower()
        return self.repository.list_users(
            wanted, limit, q, include_deleted=include_deleted
        )

    def admin_update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        status: str | None = None,
        role: str | None = None,
    ) -> User:
        self.ensure_default()
        current = self.repository.get_user(user_id)
        if current is None:
            raise AuthRequiredError("user not found")
        next_email = None
        if email is not None:
            address = email.strip().lower()
            if not EMAIL_PATTERN.match(address):
                raise ValueError("invalid email format")
            if address != current.email and self.repository.get_user_by_email(address):
                raise EmailAlreadyRegisteredError("this email is already taken")
            next_email = address
        next_status = None
        if status is not None:
            wanted = (status or "").strip().lower()
            if wanted not in USER_STATUSES:
                raise ValueError(f"unknown status: {wanted}")
            next_status = wanted
        next_name = None
        if display_name is not None:
            label = display_name.strip()
            if not label:
                raise ValueError("display name must not be empty")
            next_name = label
        updated = self.repository.update_user(
            user_id,
            display_name=next_name,
            email=next_email,
            status=next_status,
        )
        if updated is None:
            raise AuthRequiredError("user not found")
        if role is not None and role.strip():
            key = self._validate_role_key(DEFAULT_TENANT_ID, role.strip())
            existing = self.repository.get_membership(DEFAULT_TENANT_ID, user_id)
            if existing is None:
                self.repository.add_membership(DEFAULT_TENANT_ID, user_id, key)
            else:
                self.repository.update_membership_role(DEFAULT_TENANT_ID, user_id, key)
        return updated

    def set_password(self, user_id: str, new_password: str) -> None:
        self.ensure_default()
        if self.repository.get_user(user_id) is None:
            raise AuthRequiredError("user not found")
        if len(new_password or "") < 8:
            raise ValueError("new password must be at least 8 characters")
        self.repository.update_password_hash(user_id, hash_password(new_password))

    def approve_user(self, user_id: str) -> User:
        self.ensure_default()
        user = self.repository.get_user(user_id)
        if user is None:
            raise AuthRequiredError("user not found")
        updated = self.repository.update_user(user_id, status=USER_STATUS_ACTIVE)
        if updated is None:
            raise AuthRequiredError("user not found")
        self.ensure_system_membership(user_id)
        return updated

    def reject_user(self, user_id: str) -> User:
        self.ensure_default()
        user = self.repository.get_user(user_id)
        if user is None:
            raise AuthRequiredError("user not found")
        updated = self.repository.update_user(user_id, status=USER_STATUS_REJECTED)
        if updated is None:
            raise AuthRequiredError("user not found")
        return updated

    def role_in_system(self, user_id: str) -> str:
        membership = self.repository.get_membership(DEFAULT_TENANT_ID, user_id)
        return normalize_role(membership.role, "") if membership else ""

    def require(self, ctx: AuthContext | None, action: str) -> AuthContext:
        if self.mode != "required":
            if ctx is None:
                ctx = self.local_context()
            return ctx
        if ctx is None:
            raise AuthRequiredError("login required")
        if not self.can(ctx, action):
            label = ctx.role_name or ctx.role_key or ctx.role
            raise PermissionDeniedError(f"role {label} is not allowed to perform {action}")
        return ctx

    def can(self, ctx: AuthContext | None, action: str) -> bool:
        if ctx is None:
            return self.mode != "required"
        if self.mode != "required":
            return True
        return action in set(ctx.actions or ())

    def visible_series_ids(self, ctx: AuthContext | None) -> set[str] | None:
        if ctx is None or self.mode != "required":
            return None
        if normalize_scope(ctx.scope) != SCOPE_ASSIGNED:
            return None
        grants = self.repository.list_user_grants(ctx.tenant.id, ctx.user.id)
        return {grant.series_id for grant in grants}

    def can_access_series(
        self, ctx: AuthContext | None, series_id: str, level: str = "read"
    ) -> bool:
        if ctx is None or not series_id:
            return False
        if self.mode != "required":
            return True
        if normalize_scope(ctx.scope) != SCOPE_ASSIGNED:
            return True
        grant = self.repository.get_grant(series_id, ctx.user.id)
        if grant is None:
            return False
        if level == "write":
            return grant.level == "write"
        return grant.level in ("read", "write")

    def visible_piece_ids(
        self, ctx: AuthContext | None, piece_ids: list[str]
    ) -> list[str] | None:
        if ctx is None or self.mode != "required":
            return None
        if normalize_scope(ctx.scope) != SCOPE_ASSIGNED:
            return None
        granted = {
            grant.piece_id
            for grant in self.repository.list_user_piece_grants(
                ctx.tenant.id, ctx.user.id
            )
        }
        return [item for item in piece_ids if item in granted]

    def can_access_piece(
        self, ctx: AuthContext | None, piece_id: str, level: str = "read"
    ) -> bool:
        if ctx is None or not piece_id:
            return False
        if self.mode != "required":
            return True
        if normalize_scope(ctx.scope) != SCOPE_ASSIGNED:
            return True
        grant = self.repository.get_piece_grant(piece_id, ctx.user.id)
        if grant is None:
            return False
        if level == "write":
            return grant.level == "write"
        return grant.level in ("read", "write")

    def list_piece_grants(
        self, tenant_id: str, piece_id: str
    ) -> list[PieceGrant]:
        grants = self.repository.list_piece_grants(piece_id)
        return [grant for grant in grants if grant.tenant_id == tenant_id]

    def replace_piece_grants(
        self, tenant_id: str, piece_id: str, grants: list[tuple[str, str]]
    ) -> list[PieceGrant]:
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        for user_id, level in grants:
            target = (user_id or "").strip()
            if not target or target in seen:
                continue
            if self.repository.get_membership(tenant_id, target) is None:
                raise MembershipNotFoundError(f"member not found: {target}")
            seen.add(target)
            cleaned.append((target, "write" if level == "write" else "read"))
        return self.repository.replace_piece_grants(
            tenant_id, piece_id, cleaned
        )

    def list_roles(self, tenant_id: str) -> list[dict[str, Any]]:
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("tenant not found")
        roles = self.ensure_tenant_roles(tenant_id)
        payload: list[dict[str, Any]] = []
        for role in roles:
            payload.append(
                {
                    "id": role.id,
                    "key": role.key,
                    "name": role.name or role.key,
                    "actions": list(role.actions),
                    "scope": role.scope,
                    "builtin": role.builtin,
                    "member_count": self.repository.count_role_members(
                        tenant_id, role.key
                    ),
                }
            )
        return payload

    def create_role(
        self, tenant_id: str, name: str, actions: list[str], scope: str = SCOPE_ALL
    ) -> Role:
        label = (name or "").strip()
        if not label:
            raise ValueError("role name must not be empty")
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("tenant not found")
        pending = normalize_actions(actions)
        if not pending:
            raise ValueError("a role needs at least one permission")
        self.ensure_tenant_roles(tenant_id)
        key = self._unique_role_key(tenant_id, label)
        return self.repository.create_role(
            tenant_id, key, label, pending, normalize_scope(scope), builtin=False
        )

    def update_role(
        self,
        tenant_id: str,
        role_id: str,
        name: str | None = None,
        actions: list[str] | None = None,
        scope: str | None = None,
    ) -> Role:
        role = self.repository.get_role_by_id(role_id)
        if role is None or role.tenant_id != tenant_id:
            raise RoleNotFoundError("role not found")
        if role.builtin and actions is not None:
            raise BuiltinRoleError("permissions of built-in roles cannot be modified")
        next_actions = None if actions is None else normalize_actions(actions)
        if next_actions is not None and not next_actions:
            raise ValueError("a role needs at least one permission")
        if name is not None and not (name or "").strip():
            raise ValueError("role name must not be empty")
        updated = self.repository.update_role(
            role_id,
            name=(name.strip() if name is not None else None),
            actions=next_actions,
            scope=(normalize_scope(scope) if scope is not None else None),
        )
        if updated is None:
            raise RoleNotFoundError("role not found")
        return updated

    def delete_role(self, tenant_id: str, role_id: str) -> bool:
        role = self.repository.get_role_by_id(role_id)
        if role is None or role.tenant_id != tenant_id:
            raise RoleNotFoundError("role not found")
        if role.builtin:
            raise BuiltinRoleError("built-in roles cannot be deleted")
        if self.repository.count_role_members(tenant_id, role.key) > 0:
            raise RoleInUseError("members still use this role, so it cannot be deleted")
        return self.repository.delete_role(role_id)

    def list_grants(self, tenant_id: str, series_id: str) -> list[SeriesGrant]:
        grants = self.repository.list_grants(series_id)
        return [grant for grant in grants if grant.tenant_id == tenant_id]

    def replace_grants(
        self, tenant_id: str, series_id: str, grants: list[tuple[str, str]]
    ) -> list[SeriesGrant]:
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        for user_id, level in grants:
            target = (user_id or "").strip()
            if not target or target in seen:
                continue
            if self.repository.get_membership(tenant_id, target) is None:
                raise MembershipNotFoundError(f"member not found: {target}")
            seen.add(target)
            cleaned.append((target, "write" if level == "write" else "read"))
        return self.repository.replace_grants(tenant_id, series_id, cleaned)

    def capabilities(self, ctx: AuthContext) -> dict[str, Any]:
        visible = self.visible_series_ids(ctx)
        return {
            "user_id": ctx.user.id,
            "tenant_id": ctx.tenant.id,
            "tenant": {
                "id": ctx.tenant.id,
                "name": ctx.tenant.name,
                "kind": ctx.tenant.kind,
                "is_system": ctx.tenant.is_system(),
            },
            "avatar_url": ctx.user.avatar_url(),
            "role": ctx.role_payload(),
            "can": {action: self.can(ctx, action) for action in ALL_ACTIONS},
            "visible_series_ids": "all" if visible is None else sorted(visible),
        }

    def tenants_payload(self, user: User) -> list[dict[str, Any]]:
        self.ensure_default()
        payload: list[dict[str, Any]] = []
        for membership in self.repository.list_memberships(user.id):
            tenant = self.repository.get_tenant(membership.tenant_id)
            if tenant is None:
                continue
            payload.append(
                {
                    "tenant": self.tenant_payload(tenant),
                    "role": membership.role,
                    "can_transfer": (
                        normalize_role(membership.role, "viewer") == "owner"
                        and not tenant.is_system()
                    ),
                }
            )
        return payload

    def tenant_payload(self, tenant: Tenant) -> dict[str, Any]:
        data = tenant.model_dump()
        data["member_count"] = self.repository.count_members(tenant.id)
        data["is_system"] = tenant.kind == TENANT_KIND_SYSTEM
        return data

    def user_payload(self, user: User, role: str | None = None) -> dict[str, Any]:
        data = user.model_dump()
        data.pop("avatar_key", None)
        data["avatar_url"] = user.avatar_url()
        if role is not None:
            data["role"] = role
        return data

    def member_payload(self, membership: Membership) -> dict[str, Any]:
        return membership.model_dump()

    def list_tenants(self, user: User) -> list[dict[str, Any]]:
        return self.tenants_payload(user)

    def create_tenant(
        self, user: User, name: str, kind: str = TENANT_KIND_PERSONAL
    ) -> tuple[Tenant, str]:
        self.ensure_default()
        label = (name or "").strip()
        if not label:
            raise ValueError("space name must not be empty")
        wanted = (kind or TENANT_KIND_PERSONAL).strip().lower()
        if wanted not in CREATABLE_TENANT_KINDS:
            raise TenantKindError("only personal or team spaces can be created")
        tenant = self.repository.create_tenant(
            label,
            self._unique_slug(label),
            kind=wanted,
            owner_user_id=user.id,
        )
        self.repository.add_membership(tenant.id, user.id, "owner")
        self.ensure_tenant_roles(tenant.id)
        return tenant, "owner"

    def rename_tenant(self, tenant_id: str, name: str) -> Tenant:
        self.ensure_default()
        label = (name or "").strip()
        if not label:
            raise ValueError("space name must not be empty")
        current = self.repository.get_tenant(tenant_id)
        if current is None:
            raise TenantNotFoundError("tenant not found")
        updated = self.repository.update_tenant(tenant_id, name=label)
        if updated is None:
            raise TenantNotFoundError("tenant not found")
        return updated

    def delete_tenant(self, tenant_id: str) -> bool:
        self.ensure_default()
        tenant = self.repository.get_tenant(tenant_id)
        if tenant is None:
            raise TenantNotFoundError("tenant not found")
        if tenant.kind == TENANT_KIND_SYSTEM or tenant.id == DEFAULT_TENANT_ID:
            raise TenantSystemError("the system space cannot be deleted")
        return self.repository.delete_tenant(tenant_id)

    def context_for_tenant(self, user: User, tenant_id: str) -> AuthContext:
        self.ensure_default()
        membership = self.repository.get_membership(tenant_id, user.id)
        if membership is None:
            raise MembershipNotFoundError("the current user does not belong to this tenant")
        tenant = self.repository.get_tenant(tenant_id)
        if tenant is None:
            raise TenantNotFoundError("tenant not found")
        return self.context_for(user, tenant, membership.role)

    def transfer_tenant(
        self, tenant_id: str, actor_user_id: str, target_user_id: str
    ) -> Tenant:
        self.ensure_default()
        tenant = self.repository.get_tenant(tenant_id)
        if tenant is None:
            raise TenantNotFoundError("tenant not found")
        if tenant.is_system() or tenant.id == DEFAULT_TENANT_ID:
            raise TenantSystemError("ownership of the system space cannot be transferred")
        actor = self.repository.get_membership(tenant_id, actor_user_id)
        if actor is None:
            raise MembershipNotFoundError("the current user does not belong to this tenant")
        if normalize_role(actor.role, "viewer") != "owner":
            raise PermissionDeniedError("only the space owner can transfer ownership")
        target = self.repository.get_membership(tenant_id, target_user_id)
        if target is None:
            raise ValueError("the target user is not a member of this space")
        if target_user_id == actor_user_id:
            raise ValueError("the target user is already the space owner")
        self.repository.update_membership_role(tenant_id, actor_user_id, "admin")
        self.repository.update_membership_role(tenant_id, target_user_id, "owner")
        updated = self.repository.update_tenant(
            tenant_id, owner_user_id=target_user_id
        )
        return updated or tenant

    def role_in_tenant(self, user: User, tenant_id: str) -> str:
        self.ensure_default()
        membership = self.repository.get_membership(tenant_id, user.id)
        if membership is None:
            raise MembershipNotFoundError("the current user does not belong to this tenant")
        return normalize_role(membership.role, "viewer")

    def list_members(self, tenant_id: str) -> list[Membership]:
        self.ensure_default()
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("tenant not found")
        return self.repository.list_members(tenant_id)

    def add_member(self, tenant_id: str, email: str, role: str) -> Membership:
        self.ensure_default()
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("tenant not found")
        address = (email or "").strip().lower()
        if not EMAIL_PATTERN.match(address):
            raise ValueError("invalid email format")
        wanted = self._validate_role_key(tenant_id, role)
        user = self.repository.get_user_by_email(address)
        if user is None:
            user = self.repository.create_user(address, "", address.split("@")[0])
        existing = self.repository.get_membership(tenant_id, user.id)
        if existing is not None:
            updated = self.repository.update_membership_role(tenant_id, user.id, wanted)
            if updated is None:
                raise MembershipNotFoundError("member not found")
            return updated
        return self.repository.add_membership(tenant_id, user.id, wanted)

    def update_member_role(self, tenant_id: str, user_id: str, role: str) -> Membership:
        self.ensure_default()
        wanted = self._validate_role_key(tenant_id, role)
        membership = self.repository.get_membership(tenant_id, user_id)
        if membership is None:
            raise MembershipNotFoundError("member not found")
        if (
            normalize_role(membership.role, "viewer") == "owner"
            and wanted != "owner"
            and self.repository.count_owners(tenant_id) <= 1
        ):
            raise PermissionDeniedError("cannot demote the last owner of a tenant")
        updated = self.repository.update_membership_role(tenant_id, user_id, wanted)
        if updated is None:
            raise MembershipNotFoundError("member not found")
        return updated

    def remove_member(self, tenant_id: str, user_id: str) -> bool:
        self.ensure_default()
        membership = self.repository.get_membership(tenant_id, user_id)
        if membership is None:
            raise MembershipNotFoundError("member not found")
        if (
            normalize_role(membership.role, "viewer") == "owner"
            and self.repository.count_owners(tenant_id) <= 1
        ):
            raise PermissionDeniedError("cannot remove the last owner of a tenant")
        return self.repository.remove_membership(tenant_id, user_id)

    def _validate_role_key(self, tenant_id: str, role: str) -> str:
        key = normalize_role(role, "")
        if not key:
            raise ValueError("role value must not be empty")
        self.ensure_tenant_roles(tenant_id)
        if self.repository.get_role(tenant_id, key) is None:
            raise ValueError(f"role not found: {key}")
        return key

    def _unique_role_key(self, tenant_id: str, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        if not base:
            base = "role-" + secrets.token_hex(3)
        candidate = base
        suffix = 1
        while self.repository.get_role(tenant_id, candidate) is not None:
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def _unique_slug(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        if not base:
            base = "space-" + secrets.token_hex(3)
        candidate = base
        suffix = 1
        while self.repository.get_tenant_by_slug(candidate) is not None:
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate
