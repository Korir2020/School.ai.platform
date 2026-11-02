"""Plain text checks for Marian Connect. No Django imports, so they can be tested on their own."""
import re

PHONE_RE = re.compile(r"(?<!\w)\+?\d(?:[\s().-]{0,2}\d){8,}(?!\w)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
WORD_RE = re.compile(r"[^\W\d_]+")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[/_-][A-Za-z0-9]+)*")


def has_phone(text):
    return bool(PHONE_RE.search(text or ""))


def has_email(text):
    return bool(EMAIL_RE.search(text or ""))


def name_words(value):
    return [w.lower() for w in WORD_RE.findall(value or "")]


def id_tokens(text, limit=40):
    out = []
    for token in TOKEN_RE.findall(text or ""):
        if not any(ch.isdigit() for ch in token):
            continue
        if token.isdigit() and len(token) < 3:
            continue
        low = token.lower()
        if low not in out:
            out.append(low)
        if len(out) >= limit:
            break
    return out


def name_variants(first, last):
    f, l = name_words(first), name_words(last)
    if not f or not l:
        return []
    out = [f + l, l + f]
    if len(f) > 1:
        out += [f[:1] + l, l + f[:1]]
    return out


def contains_run(seq, run):
    n = len(run)
    if n == 0 or n > len(seq):
        return False
    return any(seq[i:i + n] == run for i in range(len(seq) - n + 1))


def mentions_name(seq, first, last):
    return any(contains_run(seq, v) for v in name_variants(first, last))
