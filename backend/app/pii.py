"""PII masking before any model call (enhancements design D13).

`mask(text)` replaces personal identifiers with typed placeholders so they never
leave the process towards an LLM or embedding provider:

  [PHONE]      Indian mobile numbers, optional +91/91/0 prefix, optional
               space or hyphen after the first five digits
  [ID_NUMBER]  12-digit Aadhaar-like numbers, optionally grouped 4-4-4
  [EMAIL]      email addresses
  [NAME]       the name following a self-identification cue
               ("my name is", "मेरा नाम", "माझे नाव", "mera naam")

Location words and ordinary numbers ("14 दिन", "Ward 17") are untouched. Names
without a cue are a documented limitation; the citizen UI never asks for them.
"""
import re

_DIGIT_EDGE_L = r"(?<![\d])"
_DIGIT_EDGE_R = r"(?![\d])"

_ID_NUMBER = re.compile(_DIGIT_EDGE_L + r"\d{4}[ -]?\d{4}[ -]?\d{4}" + _DIGIT_EDGE_R)
# An explicit +91 / 0091 prefix is unambiguous: match these before 12-digit IDs
# (a bare "919876543210" stays ambiguous and is masked as an ID — still masked).
_PHONE_INTL = re.compile(
    r"(?:\+|00)91[ -]?[6-9]\d{4}[ -]?\d{5}" + _DIGIT_EDGE_R
)
_PHONE = re.compile(
    _DIGIT_EDGE_L
    + r"(?:(?:\+|00)?91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}"
    + _DIGIT_EDGE_R
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Cue, then one or two name words. A trailing copula/particle is not a name.
_NAME_CUE = re.compile(
    r"(?P<cue>my name is|my name's|मेरा नाम|माझे नाव|माझं नाव|mera naam|mera nam)"
    r"(?P<sep>\s*[:,-]?\s*)"
    r"(?P<name>[^\s,.।!?0-9]+(?:\s+[^\s,.।!?0-9]+)?)",
    re.IGNORECASE,
)
_NOT_NAME = {"है", "हैं", "hai", "hain", "is", "आहे", "hoon", "हूँ", "हूं"}


def _mask_name(m: re.Match) -> str:
    words = m.group("name").split()
    kept = words[:1]
    trailing = ""
    if len(words) == 2:
        if words[1].lower() in _NOT_NAME:
            trailing = " " + words[1]
        else:
            kept = words
    if kept[0].lower() in _NOT_NAME:  # "my name is is ..." — nothing to mask
        return m.group(0)
    return f"{m.group('cue')}{m.group('sep')}[NAME]{trailing}"


def mask(text: str) -> tuple[str, dict[str, int]]:
    """(masked text, {placeholder kind: count}). Idempotent."""
    if not text:
        return text, {}
    counts: dict[str, int] = {}

    def sub(pattern: re.Pattern, repl, s: str, kind: str) -> str:
        out, n = pattern.subn(repl, s)
        if n:
            counts[kind] = counts.get(kind, 0) + n
        return out

    out = sub(_EMAIL, "[EMAIL]", text, "email")
    out = sub(_PHONE_INTL, "[PHONE]", out, "phone")
    out = sub(_ID_NUMBER, "[ID_NUMBER]", out, "id_number")  # before phones
    out = sub(_PHONE, "[PHONE]", out, "phone")
    out = sub(_NAME_CUE, _mask_name, out, "name")
    # _mask_name may decline (returns the original); recount honestly.
    if "name" in counts:
        counts["name"] = out.count("[NAME]") - text.count("[NAME]")
        if counts["name"] <= 0:
            counts.pop("name")
    return out, counts
