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
    DEFAULT_TENANT_ID,
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    ROLES,
    AuthContext,
    Membership,
    Tenant,
    User,
)
from app.ports.auth_repository import AuthRepository
from app.services.errors import (
    AuthRequiredError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    MembershipNotFoundError,
    PermissionDeniedError,
    TenantNotFoundError,
)

PBKDF2_ITERATIONS = 100_000
HASH_ALGORITHM = "sha256"
TOKEN_TTL_SECONDS = 7 * 24 * 3600
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

ACTION_SETS: dict[str, set[str]] = {
    "owner": {"read", "write", "review", "manage_members", "manage_quota"},
    "admin": {"read", "write", "review", "manage_members", "manage_quota"},
    "editor": {"read", "write", "review"},
    "viewer": {"read"},
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
    return value if value in ROLES else default


def actions_for(role: str) -> set[str]:
    return set(ACTION_SETS.get(normalize_role(role), set()))


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        secret: str = "",
        ttl_seconds: int = TOKEN_TTL_SECONDS,
        mode: str = "disabled",
    ) -> None:
        self.repository = repository
        self.secret = secret or "course-studio-dev-secret"
        self.ttl_seconds = ttl_seconds
        self.mode = (mode or "disabled").strip().lower()
        self._seeded = False

    def ensure_default(self) -> None:
        if self._seeded:
            return
        repository = self.repository
        repository.ensure_schema()
        if repository.get_tenant(DEFAULT_TENANT_ID) is None:
            repository.create_tenant(
                "默认空间", "default", "free", tenant_id=DEFAULT_TENANT_ID
            )
        if repository.get_user(DEFAULT_USER_ID) is None:
            repository.create_user(
                DEFAULT_USER_EMAIL,
                hash_password(secrets.token_hex(16)),
                "本地用户",
                user_id=DEFAULT_USER_ID,
            )
        if repository.get_membership(DEFAULT_TENANT_ID, DEFAULT_USER_ID) is None:
            repository.add_membership(DEFAULT_TENANT_ID, DEFAULT_USER_ID, "owner")
        self._seeded = True

    def local_context(self) -> AuthContext:
        self.ensure_default()
        user = self.repository.get_user(DEFAULT_USER_ID)
        tenant = self.repository.get_tenant(DEFAULT_TENANT_ID)
        if user is None or tenant is None:
            raise AuthRequiredError("本地身份初始化失败")
        return AuthContext(user=user, tenant=tenant, role="owner")

    def register(self, email: str, password: str, display_name: str = "") -> tuple[User, str]:
        self.ensure_default()
        address = (email or "").strip().lower()
        if not EMAIL_PATTERN.match(address):
            raise ValueError("邮箱格式不正确")
        if len(password or "") < 8:
            raise ValueError("密码至少 8 位")
        if self.repository.get_user_by_email(address) is not None:
            raise EmailAlreadyRegisteredError("该邮箱已注册")
        user = self.repository.create_user(address, hash_password(password), display_name)
        label = (display_name or address.split("@")[0]).strip() or address
        tenant = self.repository.create_tenant(f"{label} 的空间", self._unique_slug(label))
        self.repository.add_membership(tenant.id, user.id, "owner")
        return user, issue_token(user.id, self.secret, self.ttl_seconds)

    def login(self, email: str, password: str) -> tuple[User, str]:
        self.ensure_default()
        address = (email or "").strip().lower()
        user = self.repository.get_user_by_email(address)
        if user is None:
            raise InvalidCredentialsError("邮箱或密码不正确")
        stored = self.repository.get_password_hash(user.id)
        if not verify_password(password, stored):
            raise InvalidCredentialsError("邮箱或密码不正确")
        self.repository.touch_login(user.id)
        refreshed = self.repository.get_user(user.id) or user
        return refreshed, issue_token(user.id, self.secret, self.ttl_seconds)

    def resolve(self, token: str, tenant_id: str | None = None) -> AuthContext:
        self.ensure_default()
        user_id = parse_token(token or "", self.secret)
        if not user_id:
            raise AuthRequiredError("访问令牌无效或已过期")
        user = self.repository.get_user(user_id)
        if user is None:
            raise AuthRequiredError("访问令牌对应的用户不存在")
        memberships = self.repository.list_memberships(user.id)
        if not memberships:
            raise MembershipNotFoundError("当前用户不属于任何租户")
        target = (tenant_id or "").strip()
        if target:
            membership = next(
                (item for item in memberships if item.tenant_id == target), None
            )
            if membership is None:
                raise MembershipNotFoundError("当前用户不属于该租户")
        else:
            membership = memberships[0]
        tenant = self.repository.get_tenant(membership.tenant_id)
        if tenant is None:
            raise TenantNotFoundError("租户不存在")
        return AuthContext(user=user, tenant=tenant, role=normalize_role(membership.role, "viewer"))

    def require(self, ctx: AuthContext | None, action: str) -> AuthContext:
        if self.mode != "required":
            if ctx is None:
                ctx = self.local_context()
            return ctx
        if ctx is None:
            raise AuthRequiredError("需要登录")
        if action not in actions_for(ctx.role):
            raise PermissionDeniedError(f"角色 {ctx.role} 无权执行 {action}")
        return ctx

    def tenants_payload(self, user: User) -> list[dict[str, Any]]:
        self.ensure_default()
        payload: list[dict[str, Any]] = []
        for membership in self.repository.list_memberships(user.id):
            tenant = self.repository.get_tenant(membership.tenant_id)
            if tenant is None:
                continue
            payload.append({"tenant": tenant.model_dump(), "role": membership.role})
        return payload

    def list_tenants(self, user: User) -> list[dict[str, Any]]:
        return self.tenants_payload(user)

    def create_tenant(self, user: User, name: str) -> tuple[Tenant, str]:
        self.ensure_default()
        label = (name or "").strip()
        if not label:
            raise ValueError("租户名称不能为空")
        tenant = self.repository.create_tenant(label, self._unique_slug(label))
        self.repository.add_membership(tenant.id, user.id, "owner")
        return tenant, "owner"

    def role_in_tenant(self, user: User, tenant_id: str) -> str:
        self.ensure_default()
        membership = self.repository.get_membership(tenant_id, user.id)
        if membership is None:
            raise MembershipNotFoundError("当前用户不属于该租户")
        return normalize_role(membership.role, "viewer")

    def list_members(self, tenant_id: str) -> list[Membership]:
        self.ensure_default()
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("租户不存在")
        return self.repository.list_members(tenant_id)

    def add_member(self, tenant_id: str, email: str, role: str) -> Membership:
        self.ensure_default()
        if self.repository.get_tenant(tenant_id) is None:
            raise TenantNotFoundError("租户不存在")
        address = (email or "").strip().lower()
        if not EMAIL_PATTERN.match(address):
            raise ValueError("邮箱格式不正确")
        wanted = normalize_role(role, "")
        if not wanted:
            raise ValueError("角色取值必须是 owner/admin/editor/viewer")
        user = self.repository.get_user_by_email(address)
        if user is None:
            user = self.repository.create_user(address, "", address.split("@")[0])
        existing = self.repository.get_membership(tenant_id, user.id)
        if existing is not None:
            updated = self.repository.update_membership_role(tenant_id, user.id, wanted)
            if updated is None:
                raise MembershipNotFoundError("成员不存在")
            return updated
        return self.repository.add_membership(tenant_id, user.id, wanted)

    def update_member_role(self, tenant_id: str, user_id: str, role: str) -> Membership:
        self.ensure_default()
        wanted = normalize_role(role, "")
        if not wanted:
            raise ValueError("角色取值必须是 owner/admin/editor/viewer")
        membership = self.repository.get_membership(tenant_id, user_id)
        if membership is None:
            raise MembershipNotFoundError("成员不存在")
        if (
            normalize_role(membership.role, "viewer") == "owner"
            and wanted != "owner"
            and self.repository.count_owners(tenant_id) <= 1
        ):
            raise PermissionDeniedError("不能降级租户最后一个 owner")
        updated = self.repository.update_membership_role(tenant_id, user_id, wanted)
        if updated is None:
            raise MembershipNotFoundError("成员不存在")
        return updated

    def remove_member(self, tenant_id: str, user_id: str) -> bool:
        self.ensure_default()
        membership = self.repository.get_membership(tenant_id, user_id)
        if membership is None:
            raise MembershipNotFoundError("成员不存在")
        if (
            normalize_role(membership.role, "viewer") == "owner"
            and self.repository.count_owners(tenant_id) <= 1
        ):
            raise PermissionDeniedError("不能移除租户最后一个 owner")
        return self.repository.remove_membership(tenant_id, user_id)

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
