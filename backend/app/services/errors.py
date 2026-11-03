class LessonNotFoundError(LookupError):
    pass


class MessageNotFoundError(LookupError):
    pass


class LessonContentEmptyError(ValueError):
    pass


class EmptyLLMResponseError(RuntimeError):
    pass


class NoEvidenceError(RuntimeError):
    pass


class BlueprintNotFoundError(LookupError):
    pass


class BlueprintParseError(RuntimeError):
    pass


class AuthRequiredError(RuntimeError):
    pass


class InvalidCredentialsError(RuntimeError):
    pass


class PermissionDeniedError(RuntimeError):
    pass


class MembershipNotFoundError(RuntimeError):
    pass


class TenantNotFoundError(LookupError):
    pass


class QuotaExceededError(RuntimeError):
    pass


class EmailAlreadyRegisteredError(ValueError):
    pass


class VersionConflictError(RuntimeError):
    def __init__(self, expected: int, current: int) -> None:
        super().__init__("版本冲突：内容已被他人更新")
        self.expected = int(expected)
        self.current = int(current)


class LessonLockedError(RuntimeError):
    def __init__(self, name: str, lock: object | None = None) -> None:
        super().__init__(f"该讲正被 {name} 编辑")
        self.name = name
        self.lock = lock


class LessonLockLostError(RuntimeError):
    pass


class LockTokenMismatchError(PermissionDeniedError):
    pass


class RoleNotFoundError(LookupError):
    pass


class RoleInUseError(RuntimeError):
    pass


class BuiltinRoleError(ValueError):
    pass


class ProviderNotFoundError(LookupError):
    pass


class ProviderDisabledError(ValueError):
    pass


class ProviderInUseError(RuntimeError):
    pass


class DefaultProviderError(ValueError):
    pass


class ResearchNotFoundError(LookupError):
    pass


class ResearchParseError(RuntimeError):
    pass


class LongformNotFoundError(LookupError):
    pass


class LongformSectionNotFoundError(LookupError):
    pass
