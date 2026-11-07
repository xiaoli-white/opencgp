from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from app.models.validation import CitationCoverage, CitationGap

MARKER_PATTERN = re.compile(r"\[E\d+\]")
INLINE_CODE = re.compile(r"`[^`\n]+`")
URL_PATTERN = re.compile(r"https?://\S+")
LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.+#-]{1,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
CITATION_MIN_PARAGRAPH_CHARS = 12
MAX_REPORTED_GAPS = 12

SENTENCE_PATTERN = re.compile(
    r"[^。！？；!?\n]+?(?:[。！？；!?]|\.(?=\s|$)|(?=\n|$))"
)

EXEMPT_PREFIX = re.compile(
    r"(?i)^(?:summary|in summary|chapter summary|key takeaways|further reading|"
    r"reading guide|exercise|exercises|practice|try it|"
    r"小结|总结|本章小结|延伸阅读|阅读指南|练习|思考题|自测)"
)
SUBJECTIVE = re.compile(
    r"(?i)(?:\bin my experience\b|\bi think\b|\bi believe\b|\bi prefer\b|"
    r"\bpersonally\b|\bmy advice\b|我认为|我觉得|我的经验|个人建议|建议你)"
)
ANALOGY_OR_TRANSITION = re.compile(
    r"(?i)^(?:think of|imagine|like a|just as|consider it|"
    r"想象一下|打个比方|这就好比|如前所述|前面提到|回到上文)"
)
CODE_COMMENTARY = re.compile(
    r"(?i)(?:\bthe code\b|\bthis code\b|\bthis line\b|\bthat line\b|"
    r"\bthe line\b|\bthe snippet\b|\bthe example\b|\bin the example\b|"
    r"\bhere we\b|\bthe function\b|\bthis function\b|\bthe loop\b|"
    r"\bthe script\b|\bthe output\b|\bprints\b|"
    r"这行|这段代码|上面的代码|示例代码|该函数|这个函数|这里|输出)"
)

SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "percent",
        re.compile(r"\d+(?:\.\d+)?\s*[%％]"),
    ),
    (
        "range",
        re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:-|–|—|~|～|to)\s*\d+(?:\.\d+)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "year",
        re.compile(r"\b(?:18|19|20)\d{2}\b"),
    ),
    (
        "unit_number",
        re.compile(
            r"(?i)\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|secs?|"
            r"minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?|"
            r"kb|mb|gb|tb|pb|kib|mib|gib|bytes?|bits?|req/s|rps|qps|"
            r"ops/s|iops|fps|hz|khz|mhz|ghz|px|dpi|x|times|requests?|"
            r"users?|rows?|vectors?|documents?|chunks?|queries|tokens?)\b"
        ),
    ),
    (
        "unit_number",
        re.compile(
            r"\d+(?:\.\d+)?\s*(?:万|亿|个|条|次|秒|毫秒|微秒|纳秒|分钟|"
            r"小时|天|周|月|年|倍|人|台|种|项|页|字|行|块|层|维|"
            r"参数|节点|线程|请求|用户|文档|分块|向量|令牌|字节)"
        ),
    ),
    (
        "decimal",
        re.compile(r"\b\d+\.\d+\b"),
    ),
    (
        "currency",
        re.compile(
            r"(?:[$€£¥￥]\s*\d+(?:[.,]\d+)?)|"
            r"(?:\d+(?:\.\d+)?\s*(?:元|美元|dollars?|USD|RMB|CNY))",
            re.IGNORECASE,
        ),
    ),
    (
        "formula",
        re.compile(
            r"(?i)\bO\([^)\n]{1,20}\)|(?:Θ|Ω|θ)\s*\(|"
            r"\b(?:big-o|complexity|theorem|lemma|corollary|formula|equation|proof)\b|"
            r"(?:定理|公式|复杂度|渐进复杂度)"
        ),
    ),
    (
        "standard",
        re.compile(
            r"(?i)\b(?:RFC|ISO|IEEE|W3C|ECMA|ANSI|IETF|GB/T|GB|DIN|JIS|"
            r"UL|PCI DSS|HIPAA|GDPR)\s*[-/]?\s*\d[\w./-]*"
        ),
    ),
    (
        "attribution",
        re.compile(
            r"(?i)\b(?:according to|as (?:stated|reported|documented|described) "
            r"(?:by|in)|per (?:the )?[A-Z][A-Za-z0-9 .-]{1,40}|"
            r"research (?:shows|found|suggests)|studies? (?:show|found|suggest)|"
            r"surveys? (?:show|found)|the paper\b|et al\.)\b|"
            r"(?:根据|据统计|据[^，。；]{0,8}(?:显示|指出|报道|称)|"
            r"数据显示|报告(?:显示|指出|称)|"
            r"研究(?:表明|指出|发现)|论文(?:指出|提出|表明)|"
            r"标准(?:规定|要求)|文档(?:指出|说明))"
        ),
    ),
    (
        "product_default",
        re.compile(
            r"(?i)\b(?:by default|default(?:s| value| behavior| behaviour| "
            r"config(?:uration)?)?\s+(?:is|of|to|for)|version\s+\d|"
            r"v\d+(?:\.\d+)+|(?:api|sdk|endpoint|parameter|option|method|"
            r"function|field|header|cli|command|server)\s+(?:returns?|uses?|"
            r"accepts?|supports?|requires?|defaults?|sets?|expects?|allows?|"
            r"emits?|rejects?))\b|"
            r"(?:默认(?:值|行为|配置|参数)?\s*(?:是|为|采用|使用)|"
            r"版本\s*[:：]?\s*v?\d|接口(?:返回|默认|支持|接受|要求)|"
            r"(?:支持|返回|采用|默认使用)\s*[A-Za-z0-9_.+-]+)"
        ),
    ),
    (
        "comparative",
        re.compile(
            r"(?i)\b\d+(?:\.\d+)?\s*(?:x|times)\s+(?:faster|slower|cheaper|"
            r"more|less|higher|lower|better|worse)\b|"
            r"\b(?:faster|slower|cheaper|better|worse|more efficient|"
            r"less efficient|higher|lower)\s+than\b|"
            r"比.{0,24}(?:快|慢|省|高|低|好|差|多|少)|"
            r"(?:提升|提高|降低|减少|增加)了?\s*\d+(?:\.\d+)?\s*[%％倍]"
        ),
    ),
    (
        "history",
        re.compile(
            r"(?i)\b(?:released in|founded in|introduced in|launched in|"
            r"published in|established in)\b|"
            r"(?:成立于|发布于|诞生于|问世|首次发布|首次提出)"
        ),
    ),
    (
        "proper_claim",
        re.compile(
            r"(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9_.+#-]{1,}"
            r"(?:\s+[A-Z][A-Za-z0-9_.+#-]{1,}){0,2}\s+"
            r"(?:is|are|was|were|has|have|had|uses?|supports?|provides?|"
            r"requires?|returns?|released?|introduced?|defaults?|accepts?|"
            r"implements?|runs?|stores?|indexes?|works?|powers?|allows?|"
            r"enables?|handles?|emits?|rejects?|builds?|offers?|includes?|"
            r"contains?|describes?|defines?|represents?|becomes?|came|comes|"
            r"launched?|announced?)\b|"
            r"(?<![A-Za-z0-9_.+-])[A-Za-z][A-Za-z0-9_.+#-]{1,}"
            r"(?:\s*[（(][^）)\n]{0,24}[）)])?"
            r"(?:\s*(?:则|也|还|通常|一般|往往|会|能|可以))?\s*"
            r"(?:通过|使用|支持|提供|默认|返回|采用|实现|发布|引入|需要|"
            r"接受|运行|存储|索引|基于|负责|决定|控制|把|将|面向|"
            r"提升|降低|压缩|检查|是|为)"
        ),
    ),
)

STRONG_SIGNALS = frozenset({"attribution", "standard", "product_default"})

PUNCTUATION_END = set("。！？；.!?;")


@dataclass(frozen=True)
class ParagraphSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SentenceSpan:
    start: int
    end: int
    text: str


def mask_inline_code(text: str) -> str:
    masked = INLINE_CODE.sub(lambda match: " " * len(match.group(0)), text or "")
    return URL_PATTERN.sub(lambda match: " " * len(match.group(0)), masked)


def paragraph_spans(content: str) -> list[ParagraphSpan]:
    spans: list[ParagraphSpan] = []
    current: list[str] = []
    current_start = 0
    offset = 0
    in_fence = False

    def flush() -> None:
        nonlocal current, current_start
        if not current:
            return
        raw = "".join(current)
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        text = raw.strip()
        if text:
            spans.append(
                ParagraphSpan(
                    start=current_start + left,
                    end=current_start + right,
                    text=text,
                )
            )
        current = []

    for line in (content or "").splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            in_fence = not in_fence
            offset += len(line)
            continue
        if in_fence:
            offset += len(line)
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            flush()
            offset += len(line)
            continue
        if not current:
            current_start = offset
        current.append(line)
        offset += len(line)
    flush()
    return spans


def sentence_spans(text: str) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    for match in SENTENCE_PATTERN.finditer(text or ""):
        sentence = match.group(0)
        left = len(sentence) - len(sentence.lstrip())
        right = len(sentence.rstrip())
        if right > left:
            spans.append(
                SentenceSpan(
                    start=match.start() + left,
                    end=match.start() + right,
                    text=sentence.strip(),
                )
            )
    return spans


def factual_signals(text: str) -> list[str]:
    masked = mask_inline_code(text)
    found: list[str] = []
    for name, pattern in SIGNAL_PATTERNS:
        if pattern.search(masked):
            if name not in found:
                found.append(name)
    return found


def is_exempt_paragraph(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.startswith("[[image:"):
        return True
    if EXEMPT_PREFIX.search(stripped):
        return True
    if SUBJECTIVE.search(stripped):
        return True
    if ANALOGY_OR_TRANSITION.search(stripped):
        return True
    sentences = [item.text.strip() for item in sentence_spans(stripped) if item.text.strip()]
    if sentences and all(item.rstrip().endswith(("?", "？")) for item in sentences):
        return True
    return False


def is_code_commentary(text: str, signals: Sequence[str]) -> bool:
    if any(item in STRONG_SIGNALS for item in signals):
        return False
    return bool(CODE_COMMENTARY.search(text))


def paragraph_signals(text: str) -> list[str]:
    signals: list[str] = []
    for sentence in sentence_spans(text):
        sentence_signals = factual_signals(sentence.text)
        if not sentence_signals:
            continue
        if is_code_commentary(sentence.text, sentence_signals):
            continue
        for item in sentence_signals:
            if item not in signals:
                signals.append(item)
    return signals


def paragraph_requires_citation(text: str) -> bool:
    if is_exempt_paragraph(text):
        return False
    return bool(paragraph_signals(text))


def _evidence_mapping(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        payload = dict(item)
        return {
            "marker": str(payload.get("marker") or ""),
            "source_id": str(payload.get("source_id") or ""),
            "source_name": str(payload.get("source_name") or ""),
            "chunk_id": str(payload.get("chunk_id") or ""),
            "chunk_index": int(payload.get("chunk_index") or 0),
            "start": int(payload.get("start") or 0),
            "end": int(payload.get("end") or 0),
            "text": str(payload.get("text") or payload.get("snippet") or ""),
            "snippet": str(payload.get("snippet") or payload.get("text") or ""),
        }
    citation = getattr(item, "citation", None)
    marker = str(getattr(item, "marker", "") or "")
    if citation is not None:
        return {
            "marker": marker,
            "source_id": str(getattr(citation, "source_id", "") or ""),
            "source_name": str(getattr(citation, "source_name", "") or ""),
            "chunk_id": str(getattr(citation, "chunk_id", "") or ""),
            "chunk_index": int(getattr(citation, "chunk_index", 0) or 0),
            "start": int(getattr(citation, "start", 0) or 0),
            "end": int(getattr(citation, "end", 0) or 0),
            "text": str(
                getattr(citation, "text", "") or getattr(citation, "snippet", "") or ""
            ),
            "snippet": str(
                getattr(citation, "snippet", "") or getattr(citation, "text", "") or ""
            ),
        }
    return {
        "marker": marker,
        "source_id": str(getattr(item, "source_id", "") or ""),
        "source_name": str(getattr(item, "source_name", "") or ""),
        "chunk_id": str(getattr(item, "chunk_id", "") or ""),
        "chunk_index": int(getattr(item, "chunk_index", 0) or 0),
        "start": int(getattr(item, "start", 0) or 0),
        "end": int(getattr(item, "end", 0) or 0),
        "text": str(
            getattr(item, "text", "") or getattr(item, "snippet", "") or ""
        ),
        "snippet": str(
            getattr(item, "snippet", "") or getattr(item, "text", "") or ""
        ),
    }


def normalize_evidence(evidence: Iterable[Any] | None) -> list[dict[str, Any]]:
    items = [_evidence_mapping(item) for item in (evidence or [])]
    return [item for item in items if item.get("marker")]


def _tokens(text: str) -> set[str]:
    value = mask_inline_code(text or "")
    tokens = {match.group(0).lower() for match in LATIN_TOKEN.finditer(value)}
    for run in CJK_RUN.findall(value):
        if len(run) == 1:
            tokens.add(run)
            continue
        for index in range(len(run) - 1):
            tokens.add(run[index : index + 2])
    return tokens


def closest_marker(text: str, evidence: Sequence[dict[str, Any]]) -> str:
    if not evidence:
        return ""
    target = _tokens(text)
    if not target:
        return str(evidence[0].get("marker") or "")
    best_marker = str(evidence[0].get("marker") or "")
    best_score = -1.0
    for item in evidence:
        source = _tokens(str(item.get("text") or ""))
        source.update(_tokens(str(item.get("source_name") or "")))
        if not source:
            continue
        overlap = len(target & source)
        score = overlap / math.sqrt(max(1, len(target)))
        if score > best_score:
            best_score = score
            best_marker = str(item.get("marker") or "")
    return best_marker


def analyze_citation_coverage(
    content: str,
    policy: str,
    evidence: Iterable[Any] | None = None,
    min_chars: int = CITATION_MIN_PARAGRAPH_CHARS,
) -> CitationCoverage:
    normalized = normalize_evidence(evidence)
    spans = paragraph_spans(content or "")
    if policy == "forbidden":
        return CitationCoverage(paragraphs_total=len(spans), coverage=1.0)
    required = 0
    cited = 0
    missing: list[CitationGap] = []
    for span in spans:
        if len(span.text) < min_chars:
            continue
        if is_exempt_paragraph(span.text):
            continue
        signals = paragraph_signals(span.text)
        if not signals:
            continue
        required += 1
        if MARKER_PATTERN.search(span.text):
            cited += 1
            continue
        missing.append(
            CitationGap(
                paragraph=span.text,
                start=span.start,
                end=span.end,
                signals=signals,
                suggested_marker=closest_marker(span.text, normalized),
                reason="factual paragraph without an evidence marker",
            )
        )
    ratio = (cited / required) if required else 1.0
    return CitationCoverage(
        paragraphs_total=len(spans),
        required_paragraphs=required,
        cited_paragraphs=cited,
        coverage=round(float(ratio), 4),
        missing=missing,
    )


def _insert_marker(paragraph: str, sentence: SentenceSpan, marker: str) -> str:
    segment = paragraph[: sentence.end]
    trailing = segment[len(segment.rstrip()) :]
    core = segment.rstrip()
    if not core:
        return paragraph
    if core[-1] in PUNCTUATION_END:
        insert_at = len(core) - 1
        before = core[:insert_at].rstrip()
        after = core[insert_at:]
    else:
        before = core
        after = ""
    return before + f" [{marker}]" + after + trailing + paragraph[sentence.end :]


def attach_citation_markers(
    content: str,
    coverage: CitationCoverage,
    evidence: Iterable[Any] | None = None,
    policy: str = "required",
    min_chars: int = CITATION_MIN_PARAGRAPH_CHARS,
) -> tuple[str, CitationCoverage]:
    if not coverage.missing:
        return content, coverage
    normalized = normalize_evidence(evidence)
    updated = content
    for gap in sorted(coverage.missing, key=lambda item: item.start, reverse=True):
        if gap.start < 0 or gap.end > len(updated) or gap.start >= gap.end:
            continue
        paragraph = updated[gap.start : gap.end]
        marker = gap.suggested_marker or closest_marker(paragraph, normalized)
        if not marker:
            continue
        target: SentenceSpan | None = None
        for sentence in sentence_spans(paragraph):
            signals = factual_signals(sentence.text)
            if not signals or MARKER_PATTERN.search(sentence.text):
                continue
            if is_code_commentary(sentence.text, signals):
                continue
            target = sentence
            break
        if target is None:
            target = SentenceSpan(start=0, end=len(paragraph), text=paragraph)
        replacement = _insert_marker(paragraph, target, marker)
        updated = updated[: gap.start] + replacement + updated[gap.end :]
    return updated, analyze_citation_coverage(
        updated, policy, normalized, min_chars=min_chars
    )
