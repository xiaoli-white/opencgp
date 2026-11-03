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
