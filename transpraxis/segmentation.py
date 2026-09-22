"""Deterministic source segmentation for the CAT workbench.

Source extraction and OCR cleanup intentionally remain paragraph-oriented: the
cleanup model needs the surrounding physical layout to repair broken lines and
paragraph boundaries.  Translation, however, works better with sentence-sized
units.  This module is the small, deterministic boundary between those two
contracts.

The splitter is deliberately conservative.  It never joins neighbouring
paragraphs, does not split on commas/colons/semicolons, and keeps headings,
list items, table-like rows, URLs, e-mail addresses, abbreviations and decimal
numbers intact.  Ambiguous material remains one CAT unit and can still be
edited or split manually in the workbench.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple


RULES_VERSION = 1
DEFAULT_MODE = "sentence"
SUPPORTED_MODES = ("sentence", "paragraph")

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LIST_RE = re.compile(
    r"^\s*(?:[-*+•◦▪·‣]\s+|\(?\d+[.)]\s+|[A-Za-z][.)]\s+|"
    r"[一二三四五六七八九十百千万]+[、.)]\s*)"
)
_HEADING_RE = re.compile(
    r"^\s*(?:chapter|part|section|appendix|volume|book|contents|"
    r"figure|table|preface|introduction|conclusion)\b",
    re.IGNORECASE,
)
_URL_EMAIL_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+\.\S+", re.IGNORECASE)
_ABBREVIATIONS = {
    "asap", "approx", "dept", "dr", "e.g", "etc", "fig", "i.e", "inc", "jan",
    "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "jr", "misc", "mr", "mrs", "ms", "prof", "sr", "st",
    "vs", "no",
}
_NON_TERMINAL_ABBREVIATIONS = {
    "approx", "dept", "dr", "e.g", "fig", "i.e", "inc", "jan", "feb", "mar",
    "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "jr",
    "misc", "mr", "mrs", "ms", "prof", "sr", "st", "vs", "no",
}
_CLOSING_CHARS = set('"\'”’»)]}】》」』〉〕）］〗〙〛')
_SENTENCE_CHARS = set(".!?。！？")


def resolve_mode(value: Any = None, fallback: Any = None,
                 environment: Any = None, default: Any = DEFAULT_MODE) -> str:
    """Resolve a user/configured mode without allowing an unknown value."""
    for candidate in (value, fallback, environment, default, DEFAULT_MODE):
        mode = str(candidate or "").strip().lower()
        if mode in SUPPORTED_MODES:
            return mode
    return DEFAULT_MODE


def _has_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(value or ""))


def _normalise_spaces(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _preserved_list_or_table_parts(raw: str, text: str) -> List[str] | None:
    lines = [_normalise_spaces(line) for line in str(raw or "").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) > 1 and all(_LIST_RE.match(line) for line in lines):
        # List items are already structural units.  Keep each item together,
        # but do not make two neighbouring bullets one CAT segment.
        return lines
    if _LIST_RE.match(text):
        return [text]
    # A tab or multiple pipe separators are strong evidence that this is a
    # table row.  Keep it together; splitting a row would destroy columns.
    if "\t" in str(raw or "") or text.count("|") >= 2:
        return [text]
    return None


def _looks_like_heading(text: str) -> bool:
    if not text or len(text) > 180:
        return False
    if _HEADING_RE.match(text):
        return True
    if text.isupper() and len(text.split()) <= 18:
        return True
    # Short title-case lines without a terminal mark are usually headings.  Do
    # not classify a normal long prose paragraph this way.
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
    if (words and len(words) <= 12 and not re.search(r"[.!?。！？]$", text)
            and sum(1 for word in words if word[:1].isupper()) >= max(2, len(words) // 2)):
        return True
    return False


def _token_before(text: str, index: int) -> str:
    """Return the word/dotted abbreviation ending immediately before ``index``."""
    prefix = text[:index]
    match = re.search(r"([A-Za-z](?:[A-Za-z.]*)?)$", prefix)
    return match.group(1) if match else ""


def _dot_is_boundary(text: str, index: int) -> bool:
    """Decide whether a period is sentence punctuation rather than an inline dot."""
    if index + 1 < len(text) and text[index + 1] == ".":
        return False
    before = text[index - 1] if index else ""
    next_index = index + 1
    while next_index < len(text) and text[next_index] in _CLOSING_CHARS:
        next_index += 1
    after = text[next_index] if next_index < len(text) else ""
    if before.isdigit() and after.isdigit():
        return False
    # Dotted domains, e-mail addresses, and paths are never boundaries at an
    # inline dot.  A final period after a URL is still allowed below.
    line_start = max(text.rfind(" ", 0, index), text.rfind("\n", 0, index)) + 1
    token = text[line_start:index + 1]
    if ("@" in token or "://" in token or token.lower().startswith("www.")) \
            and after and not after.isspace():
        return False
    word = _token_before(text, index).casefold().rstrip(".")
    if word in _ABBREVIATIONS:
        if word in _NON_TERMINAL_ABBREVIATIONS:
            return False
        # Abbreviations such as ``etc.`` can also end a sentence.  Treat them
        # as a boundary only when the following token looks like a sentence
        # start; lowercase continuations remain atomic.
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if next_index >= len(text):
            return True
        next_char = text[next_index]
        return next_char.isupper() or _has_cjk(next_char) \
            or next_char.isdigit() or next_char in '"\'“‘（([{'
    if len(word) == 1 and word.isalpha():
        return False
    # Initials such as U.S.A. are covered even when the complete dotted token
    # is longer than the small abbreviation list.
    if re.search(r"(?:[a-z]\.){2,}[a-z]?\s*$",
                 text[max(0, index - 12):index + 1].casefold()):
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if next_index >= len(text):
            return True
        next_char = text[next_index]
        return next_char.isupper() or _has_cjk(next_char) \
            or next_char.isdigit() or next_char in '"\'“‘（([{'
    if after and not after.isspace():
        # A period embedded in a word or URL cannot finish the sentence.
        return False
    if not after:
        return True
    while next_index < len(text) and text[next_index].isspace():
        next_index += 1
    if next_index >= len(text):
        return True
    next_char = text[next_index]
    # English sentence starts conventionally use an uppercase letter.  CJK
    # text does not need a space or case distinction, but CJK terminals are
    # handled independently by the scanner.
    return next_char.isupper() or _has_cjk(next_char) or next_char.isdigit() \
        or next_char in '"\'“‘（([{'


def _boundary_end(text: str, index: int) -> int:
    """Consume repeated terminal punctuation, closing quotes and whitespace."""
    end = index + 1
    while end < len(text) and text[end] in _SENTENCE_CHARS:
        end += 1
    while end < len(text) and text[end] in _CLOSING_CHARS:
        end += 1
    return end


def _split_sentences(raw: str) -> List[str]:
    text = _normalise_spaces(raw)
    if not text:
        return []
    preserved = _preserved_list_or_table_parts(raw, text)
    if preserved is not None or _looks_like_heading(text):
        return preserved or [text]
    # A standalone URL/e-mail is an atomic unit even if it contains dots.
    if _URL_EMAIL_RE.fullmatch(text):
        return [text]

    result: List[str] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        boundary = char in "!?。！？" or (char == "." and _dot_is_boundary(text, index))
        if boundary:
            end = _boundary_end(text, index)
            candidate = text[start:end].strip()
            if candidate:
                result.append(candidate)
            start = end
            index = end
            continue
        index += 1
    tail = text[start:].strip()
    if tail:
        result.append(tail)
    return result or [text]


def segment_paragraphs(
    paragraphs: Sequence[Any], *, mode: Any = DEFAULT_MODE,
    source_lang: Any = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """Build ordered CAT units from cleaned source paragraphs.

    The returned metadata is intentionally compact: paragraph ranges let the
    UI/audit map each sentence back to its recovered paragraph without storing
    a second copy of every segment in ``state.json``.
    """
    resolved = resolve_mode(mode)
    values = [str(item or "").strip() for item in paragraphs]
    if resolved == "paragraph":
        segments = values
        ranges = [
            {"paragraph_index": index, "start": index, "end": index + 1}
            for index in range(len(values))
        ]
    else:
        segments = []
        ranges = []
        for paragraph_index, paragraph in enumerate(values):
            start = len(segments)
            parts = _split_sentences(paragraph)
            segments.extend(parts)
            ranges.append({
                "paragraph_index": paragraph_index,
                "start": start,
                "end": len(segments),
            })

    split_paragraphs = sum(
        1 for item in ranges if int(item["end"]) - int(item["start"]) > 1
    )
    metadata: Dict[str, Any] = {
        "rules_version": RULES_VERSION,
        "mode": resolved,
        "source_lang": str(source_lang or "").strip(),
        "input_paragraph_count": len(values),
        "output_segment_count": len(segments),
        "split_paragraph_count": split_paragraphs,
        "preserved_paragraph_count": len(values) - split_paragraphs,
        "paragraph_ranges": ranges,
    }
    return segments, metadata


__all__ = ["DEFAULT_MODE", "RULES_VERSION", "SUPPORTED_MODES",
           "resolve_mode", "segment_paragraphs"]
