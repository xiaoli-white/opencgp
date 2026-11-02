from __future__ import annotations

from typing import Sequence

Span = tuple[int, int]


def paragraph_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    start = 0
    length = len(text)
    index = 0
    while index < length:
        if text[index] == "\n":
            run_end = index
            while run_end < length and text[run_end] == "\n":
                run_end += 1
            segment = text[start:index]
            if segment.strip():
                spans.append((_trim_start(start, segment), _trim_end(index, segment)))
            start = run_end
            index = run_end
            continue
        index += 1
    tail = text[start:]
    if tail.strip():
        spans.append((_trim_start(start, tail), _trim_end(len(text), tail)))
    return [span for span in spans if span[1] > span[0]]


def _trim_start(start: int, segment: str) -> int:
    return start + (len(segment) - len(segment.lstrip()))


def _trim_end(end: int, segment: str) -> int:
    return end - (len(segment) - len(segment.rstrip()))


def _windows(start: int, end: int, max_chars: int, overlap: int) -> list[Span]:
    spans: list[Span] = []
    pos = start
    while pos < end:
        stop = min(pos + max_chars, end)
        spans.append((pos, stop))
        if stop >= end:
            break
        pos = max(stop - overlap, pos + 1)
    return spans


def chunk_spans(
    text: str, max_chars: int = 800, overlap: int = 120
) -> list[Span]:
    if max_chars <= 0:
        raise ValueError("max_chars 必须为正整数")
    overlap = max(0, min(overlap, max_chars // 2))
    paragraphs = paragraph_spans(text)
    if not paragraphs:
        return []

    pieces: list[Span] = []
    for start, end in paragraphs:
        if end - start <= max_chars:
            pieces.append((start, end))
        else:
            pieces.extend(_windows(start, end, max_chars, overlap))

    chunks: list[Span] = []
    current_start, current_end = pieces[0]
    for start, end in pieces[1:]:
        if end - current_start <= max_chars:
            current_end = end
            continue
        chunks.append((current_start, current_end))
        anchor = current_end - overlap
        next_start = start
        for piece_start, piece_end in pieces:
            if piece_end > anchor:
                next_start = min(piece_start, start)
                break
        current_start = max(min(next_start, start), 0)
        current_end = end
    chunks.append((current_start, current_end))
    return [(start, end) for start, end in chunks if end > start]


def chunk_texts(
    text: str, max_chars: int = 800, overlap: int = 120
) -> list[tuple[int, int, str]]:
    results: list[tuple[int, int, str]] = []
    for start, end in chunk_spans(text, max_chars, overlap):
        body = text[start:end].strip()
        if body:
            results.append((start, end, body))
    return results


def split_sentences(text: str) -> Sequence[str]:
    marks = "。！？；\n"
    sentences: list[str] = []
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in marks:
            sentence = "".join(buffer).strip()
            if sentence:
                sentences.append(sentence)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    return sentences
