from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from app.services.topic_aliases import DEFAULT_TOPIC_ALIASES

CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")
CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]{2,}")
CJK_ORDINAL_RE = re.compile(
    r"第[一二三四五六七八九十百千万零〇0-9]+(?:讲|课|章|节|单元|部分|篇)"
)
CJK_PARTICLES_RE = re.compile(r"[的了和与及或在是有为对把被将让给从到就都也还很更最太不没无并要中该其此每各所]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.\-]{1,}")
LATIN_WORD_BOUNDARY = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"

CJK_GENERIC_TERMS = (
    "基本原理",
    "基本概念",
    "核心概念",
    "知识点",
    "知识点",
    "学习目标",
    "教学目标",
    "课程目标",
    "主要内容",
    "相关知识",
    "应用场景",
    "代码实现",
    "实践应用",
    "案例分析",
    "课程内容",
    "教学大纲",
    "第一讲",
    "第二讲",
    "第三讲",
    "第四讲",
    "第五讲",
    "阶段",
    "模块",
    "环节",
    "讲次",
    "说明",
    "解释",
    "自己的话",
    "给出",
    "具体",
    "例子",
    "判断",
    "适用",
    "边界",
    "核心",
    "术语",
    "定义",
    "步骤",
    "流程",
    "示例",
    "场景",
    "作用",
    "意义",
    "特点",
    "优势",
    "劣势",
    "注意",
    "建议",
    "回顾",
    "导入",
    "小结",
    "思考",
    "讨论",
    "测验",
    "考试",
    "大纲",
    "学时",
    "要求",
    "关键",
    "培养",
    "训练",
    "任务",
    "活动",
    "习题",
    "答案",
    "解析",
    "点评",
    "反馈",
    "改进",
    "优化",
    "提升",
    "拓展",
    "延伸",
    "阅读",
    "参考",
    "文献",
    "资料",
    "资源",
    "网站",
    "链接",
    "函数",
    "变量",
    "参数",
    "配置",
    "安装",
    "运行",
    "部署",
    "调试",
    "测试",
    "性能",
    "并发",
    "架构",
    "原理",
    "思路",
    "学习",
    "目标",
    "单元",
    "课程",
    "章节",
    "教程",
    "入门",
    "进阶",
    "实战",
    "基础",
    "概述",
    "简介",
    "总结",
    "指南",
    "技巧",
    "经验",
    "分享",
    "笔记",
    "介绍",
    "讲解",
    "内容",
    "部分",
    "系列",
    "如何",
    "什么",
    "为什么",
    "怎么",
    "以及",
    "并且",
    "其中",
    "根据",
    "对于",
    "关于",
    "完成",
    "认识",
    "体会",
    "感受",
    "欣赏",
    "评价",
    "综合",
    "运用",
    "迁移",
    "创新",
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "可以",
    "需要",
    "使用",
    "进行",
    "通过",
    "一个",
    "本文",
    "主要",
    "相关",
    "方面",
    "问题",
    "情况",
    "时候",
    "方式",
    "实现",
    "理解",
    "掌握",
    "了解",
    "熟悉",
    "能够",
    "能力",
    "知识",
    "理论",
    "实践",
    "应用",
    "案例",
    "练习",
    "作业",
    "项目",
    "复习",
    "考核",
    "评估",
    "重点",
    "难点",
    "编写",
    "构建",
    "设计",
    "分析",
    "研究",
    "技术",
    "系统",
    "工具",
    "平台",
)

LATIN_GENERIC_TERMS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "about",
        "your",
        "you",
        "are",
        "was",
        "were",
        "will",
        "what",
        "when",
        "where",
        "how",
        "why",
        "not",
        "but",
        "all",
        "any",
        "can",
        "has",
        "have",
        "its",
        "our",
        "their",
        "they",
        "them",
        "then",
        "than",
        "also",
        "such",
        "very",
        "more",
        "most",
        "some",
        "one",
        "two",
        "use",
        "using",
        "used",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "is",
        "it",
        "as",
        "an",
        "or",
        "if",
        "be",
        "do",
        "does",
        "we",
        "i",
        "unit",
        "units",
        "lesson",
        "lessons",
        "lecture",
        "lectures",
        "course",
        "courses",
        "chapter",
        "chapters",
        "section",
        "sections",
        "learning",
        "objective",
        "objectives",
        "goal",
        "goals",
        "study",
        "tutorial",
        "tutorials",
        "guide",
        "guides",
        "series",
        "class",
        "classes",
        "part",
        "introduction",
        "overview",
        "advanced",
        "basics",
        "notes",
        "note",
        "practice",
        "project",
        "projects",
        "review",
        "summary",
        "topic",
        "topics",
        "content",
        "contents",
        "material",
        "materials",
        "concept",
        "concepts",
        "example",
        "examples",
        "learn",
        "teach",
        "teaching",
    }
)


@dataclass(frozen=True)
class TopicTerm:
    text: str
    language: str
    variants: tuple[str, ...] = ()
    primary: bool = False


@dataclass
class TopicProfile:
    terms: list[TopicTerm] = field(default_factory=list)
    language: str = "unknown"
    sources: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.terms)

    @property
    def term_texts(self) -> list[str]:
        return [term.text for term in self.terms]

    def payload(self) -> dict[str, object]:
        return {
            "available": self.available,
            "language": self.language,
            "terms": self.term_texts,
            "primary_terms": [term.text for term in self.terms if term.primary],
            "variants": {term.text: list(term.variants) for term in self.terms},
        }


@dataclass
class TopicMatch:
    matched: bool
    matched_terms: list[str] = field(default_factory=list)
    passage_languages: list[str] = field(default_factory=list)
    query_language: str = "unknown"
    min_matches: int = 1
    primary_matched: bool = False
    reason: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "matched_terms": list(self.matched_terms),
            "passage_languages": list(self.passage_languages),
            "query_language": self.query_language,
            "min_matches": self.min_matches,
            "primary_matched": self.primary_matched,
            "reason": self.reason,
        }


def _casefold(value: str) -> str:
    return (value or "").casefold().strip()


def _cjk_chars(value: str) -> str:
    return "".join(CJK_CHAR_RE.findall(value or ""))


def _latin_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for match in LATIN_TOKEN_RE.finditer(value or ""):
        token = _casefold(match.group(0).strip(".-_+"))
        if token:
            tokens.add(token)
    return tokens


def _term_language(value: str) -> str:
    has_cjk = bool(CJK_CHAR_RE.search(value or ""))
    has_latin = bool(re.search(r"[A-Za-z]", value or ""))
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "zh"
    if has_latin:
        return "en"
    return "unknown"


def _query_language(terms: Sequence[TopicTerm]) -> str:
    has_zh = False
    has_en = False
    for term in terms:
        if term.language in ("zh", "mixed"):
            has_zh = True
        if term.language in ("en", "mixed"):
            has_en = True
    if has_zh and has_en:
        return "mixed"
    if has_zh:
        return "zh"
    if has_en:
        return "en"
    return "unknown"


def _strip_cjk_generic(text: str) -> str:
    cleaned = CJK_ORDINAL_RE.sub(" ", text or "")
    for word in sorted(CJK_GENERIC_TERMS, key=len, reverse=True):
        if word:
            cleaned = cleaned.replace(word, " ")
    cleaned = CJK_PARTICLES_RE.sub(" ", cleaned)
    return cleaned


def _clean_latin_token(token: str) -> str:
    return token.strip(".-_+#").strip()


def extract_topic_terms(
    texts: Sequence[str],
    *,
    max_terms: int = 8,
) -> list[str]:
    limit = max(1, int(max_terms or 1))
    seen: set[str] = set()
    latin: list[str] = []
    cjk: list[str] = []
    for text in texts:
        raw = str(text or "")
        if not raw.strip():
            continue
        for match in LATIN_TOKEN_RE.finditer(raw):
            token = _clean_latin_token(match.group(0))
            key = _casefold(token)
            if len(key) < 2 or key in LATIN_GENERIC_TERMS or key in seen:
                continue
            if key.isdigit():
                continue
            seen.add(key)
            latin.append(key)
        cleaned = _strip_cjk_generic(raw)
        for match in CJK_RUN_RE.finditer(cleaned):
            term = match.group(0)
            if len(term) > 12:
                term = term[:12]
            key = _casefold(term)
            if len(key) < 2 or key in seen:
                continue
            seen.add(key)
            cjk.append(term)
    combined = [*latin, *cjk]
    return combined[:limit]


def _synonym_overlap(term: str, candidate: str) -> bool:
    left = _casefold(term)
    right = _casefold(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    left_cjk = _cjk_chars(left)
    right_cjk = _cjk_chars(right)
    if left_cjk and right_cjk:
        return left_cjk in right_cjk or right_cjk in left_cjk
    left_latin = _latin_tokens(left)
    right_latin = _latin_tokens(right)
    if left_latin and right_latin:
        for item in left_latin:
            for other in right_latin:
                if item == other:
                    return True
                if len(item) >= 3 and len(other) >= 3 and (
                    item.startswith(other) or other.startswith(item)
                ):
                    return True
    return False


def expand_variants(
    term: str,
    alias_map: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    aliases = alias_map or DEFAULT_TOPIC_ALIASES
    variants: list[str] = [term]
    seen = {_casefold(term)}
    for canonical, values in aliases.items():
        group = (canonical, *tuple(values or ()))
        if not any(_synonym_overlap(term, candidate) for candidate in group):
            continue
        for candidate in group:
            key = _casefold(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            variants.append(str(candidate))
    return tuple(variants)


def build_topic_profile(
    texts: Sequence[str],
    *,
    alias_map: Mapping[str, Sequence[str]] | None = None,
    max_terms: int = 8,
    primary_count: int = 1,
) -> TopicProfile:
    resolved_texts = [str(text or "") for text in texts]
    primary_slice = resolved_texts[: max(1, int(primary_count or 1))]
    primary_terms = extract_topic_terms(primary_slice, max_terms=max_terms)
    all_terms = extract_topic_terms(resolved_texts, max_terms=max_terms)
    ordered: list[str] = []
    for term in [*primary_terms, *all_terms]:
        if term not in ordered:
            ordered.append(term)
    ordered = ordered[: max(1, int(max_terms or 1))]
    primary_keys = {_casefold(term) for term in primary_terms}
    if not primary_keys:
        primary_keys = {_casefold(term) for term in ordered}
    resolved: list[TopicTerm] = []
    for term in ordered:
        resolved.append(
            TopicTerm(
                text=term,
                language=_term_language(term),
                variants=expand_variants(term, alias_map),
                primary=_casefold(term) in primary_keys,
            )
        )
    return TopicProfile(
        terms=resolved,
        language=_query_language(resolved),
        sources=[text for text in resolved_texts if text.strip()],
    )


def passage_languages(text: str) -> list[str]:
    body = str(text or "")
    cjk_count = len(CJK_CHAR_RE.findall(body))
    latin_words = len(LATIN_TOKEN_RE.findall(body))
    if not cjk_count and not latin_words:
        return []
    cjk_ratio = cjk_count / max(1, cjk_count + latin_words * 4)
    languages: list[str] = []
    if cjk_count and (cjk_ratio >= 0.15 or cjk_count >= 20):
        languages.append("zh")
    if latin_words and cjk_ratio < 0.15:
        languages.append("en")
    return languages


def _variant_matches(
    variant: str,
    body: str,
    languages: Sequence[str],
    term_language: str,
) -> bool:
    language = _term_language(variant)
    if term_language == "zh" and language == "en":
        return False
    if term_language == "en" and language == "zh":
        return False
    if language == "zh" and "zh" not in languages:
        return False
    if language == "en" and "en" not in languages:
        return False
    if language == "mixed" and not languages:
        return False
    if CJK_CHAR_RE.search(variant):
        return _casefold(variant) in _casefold(body)
    pattern = re.compile(
        LATIN_WORD_BOUNDARY.format(re.escape(variant.strip())),
        re.IGNORECASE,
    )
    return bool(pattern.search(body))


def match_passage(
    text: str,
    profile: TopicProfile,
    *,
    min_matches: int = 1,
) -> TopicMatch:
    required = max(1, int(min_matches or 1))
    if not profile.available:
        return TopicMatch(
            matched=False,
            query_language=profile.language,
            min_matches=required,
            reason="no_topic_terms",
        )
    languages = passage_languages(text)
    matched: list[str] = []
    primary_matched = False
    has_primary = any(term.primary for term in profile.terms)
    for term in profile.terms:
        for variant in term.variants:
            if _variant_matches(
                variant, str(text or ""), languages, term.language
            ):
                matched.append(term.text)
                if term.primary:
                    primary_matched = True
                break
    enough = len(matched) >= required
    accepted = enough and (primary_matched or not has_primary)
    reason = ""
    if not accepted:
        if not enough:
            reason = "no_topic_terms_in_passage"
        else:
            reason = "no_primary_topic_term_in_passage"
    return TopicMatch(
        matched=accepted,
        matched_terms=matched,
        passage_languages=languages,
        query_language=profile.language,
        min_matches=required,
        primary_matched=primary_matched,
        reason=reason,
    )


def is_topical(
    text: str,
    profile: TopicProfile,
    *,
    min_matches: int = 1,
) -> bool:
    return match_passage(text, profile, min_matches=min_matches).matched
