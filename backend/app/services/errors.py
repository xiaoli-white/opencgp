class LessonNotFoundError(LookupError):
    pass


class MessageNotFoundError(LookupError):
    pass


class LessonContentEmptyError(ValueError):
    pass


class EmptyLLMResponseError(RuntimeError):
    pass
