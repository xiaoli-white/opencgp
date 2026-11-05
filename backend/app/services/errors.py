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


class MembershipNotFoundError(RuntimeError):
    pass


class PermissionDeniedError(RuntimeError):
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


class JobNotFoundError(LookupError):
    pass


class UnsupportedJobKindError(ValueError):
    pass


class AccountNotActiveError(PermissionDeniedError):
    pass


class AvatarInvalidError(ValueError):
    pass


class TenantInUseError(RuntimeError):
    pass


class TenantKindError(ValueError):
    pass


class TenantSystemError(ValueError):
    pass


class JobNotTerminalError(RuntimeError):
    pass


class UserDeleteForbiddenError(ValueError):
    pass


class UserHasWorksError(RuntimeError):
    pass


class CreationProfileNotFoundError(LookupError):
    pass


class SourceNotFoundError(LookupError):
    pass


class ThreadNotFoundError(LookupError):
    pass


class ExportSourceNotFoundError(LookupError):
    pass


class ExportFormatError(ValueError):
    pass


class ExportUnavailableError(RuntimeError):
    pass


class ImageGenerationUnavailableError(RuntimeError):
    pass


class ImageGenerationError(RuntimeError):
    pass


class MediaAssetNotFoundError(LookupError):
    pass


class ExecUnavailableError(RuntimeError):
    pass


class ExecLanguageError(ValueError):
    pass


class MediaInvalidError(ValueError):
    pass


class ProviderCallError(RuntimeError):
    def __init__(self, detail: str = "") -> None:
        reason = (detail or "未知原因").strip()[:120]
        super().__init__(f"模型通道调用失败：{reason}")
        self.detail = reason


class ProfileNotFoundError(LookupError):
    pass


class BuiltinProfileError(ValueError):
    pass


class ProfileInUseError(RuntimeError):
    pass


class ProfileInvalidError(ValueError):
    pass


class ShareNotFoundError(Exception):
    pass


class ShareRevokedError(Exception):
    pass


class ShareExpiredError(Exception):
    pass


class ShareRateLimitedError(Exception):
    pass


class QueueUnavailableError(RuntimeError):
    pass
