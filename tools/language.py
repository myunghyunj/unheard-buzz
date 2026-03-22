"""
Shared language helpers for collector-side filtering.

The detection flow is intentionally lightweight:
1. Script detection for languages with distinctive Unicode ranges
2. Stopword heuristics for a few Latin-script languages
3. Optional langdetect fallback if the package is installed
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


_WORD_RE = re.compile(r"[a-z\u00c0-\u024f']+")

_STOPWORD_HINTS = {
    "en": {"the", "and", "is", "are", "with", "for", "that", "this", "you"},
    "fr": {"le", "la", "les", "et", "est", "avec", "pour", "dans", "des"},
    "de": {"der", "die", "das", "und", "ist", "mit", "nicht", "für", "ein"},
    "es": {"el", "la", "los", "las", "y", "es", "con", "para", "que"},
    "it": {"il", "lo", "la", "gli", "e", "con", "per", "che", "non"},
    "pt": {"o", "a", "os", "as", "e", "com", "para", "que", "não"},
}


def _guess_by_script(sample: str) -> Optional[str]:
    if re.search(r"[가-힣]", sample):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", sample):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", sample):
        return "zh"
    if re.search(r"[\u0400-\u04FF]", sample):
        return "ru"
    return None


def _guess_by_stopwords(sample: str) -> Optional[str]:
    tokens = [tok.lower() for tok in _WORD_RE.findall(sample)]
    if len(tokens) < 3:
        return None

    scores = {
        lang: sum(1 for tok in tokens if tok in hints)
        for lang, hints in _STOPWORD_HINTS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None

    best_lang, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if best_score >= 3 and best_score > second_score:
        return best_lang
    return None


def _normalize_lang_code(code: str) -> Optional[str]:
    code = (code or "").strip().lower()
    if not code:
        return None
    if code.startswith("zh"):
        return "zh"
    if code.startswith("pt"):
        return "pt"
    if code.startswith("en"):
        return "en"
    if code.startswith("fr"):
        return "fr"
    if code.startswith("de"):
        return "de"
    if code.startswith("es"):
        return "es"
    if code.startswith("it"):
        return "it"
    if code.startswith("ja"):
        return "ja"
    if code.startswith("ko"):
        return "ko"
    if code.startswith("ru"):
        return "ru"
    return code.split("-")[0]


def _guess_by_langdetect(sample: str) -> Optional[str]:
    if len(sample.strip()) < 40:
        return None

    try:
        from langdetect import detect  # type: ignore
        from langdetect.lang_detect_exception import LangDetectException  # type: ignore
    except ImportError:
        return None

    try:
        return _normalize_lang_code(detect(sample))
    except LangDetectException:
        return None


def guess_language(text: str) -> str:
    sample = (text or "")[:500]
    if not sample.strip():
        return "unknown"

    for guesser in (_guess_by_script, _guess_by_stopwords, _guess_by_langdetect):
        lang = guesser(sample)
        if lang:
            return lang
    return "unknown"


def language_allowed(lang: str, allowlist: Iterable[str]) -> bool:
    allowed = {str(item).lower() for item in (allowlist or []) if str(item).strip()}
    if not allowed:
        return True
    return str(lang).lower() in allowed
