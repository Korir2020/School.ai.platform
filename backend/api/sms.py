"""SMS delivery. Provider is chosen by environment variables only.

DJANGO_SMS_PROVIDER = "africastalking" | "console" | "" (off, the default)
  africastalking: DJANGO_AT_USERNAME, DJANGO_AT_API_KEY, optional DJANGO_AT_SENDER_ID
                  (username "sandbox" uses the Africa's Talking sandbox).
  console:        prints messages to the server log (developer machines only).

We never pretend: when no provider is configured nothing is sent and every
number is reported as "not_configured". Message text is never logged in
production because it may contain codes or personal details.
"""
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

MAX_LEN = 459          # three SMS segments
BATCH = 100            # numbers per provider request
LIVE_URL = "https://api.africastalking.com/version1/messaging"
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
_OK_CODES = {100, 101, 102}  # processed, sent, queued


def provider():
    p = os.environ.get("DJANGO_SMS_PROVIDER", "").strip().lower()
    if p == "africastalking" and os.environ.get("DJANGO_AT_USERNAME") and os.environ.get("DJANGO_AT_API_KEY"):
        return "africastalking"
    if p == "console":
        return "console"
    return ""


def is_configured():
    return provider() != ""


def normalize_phone(raw, country_code="254"):
    """Return an E.164 number (+2547XXXXXXXX) or "" when the input is not a phone number.
    Accepts 07.., 01.., 7.., 1.., 2547.., +2547.. and spaces, dashes or brackets."""
    if not raw:
        return ""
    s = re.sub(r"[\s\-().]", "", str(raw))
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        digits = s[1:]
    elif s.startswith(country_code):
        digits = s
    elif s.startswith("0") and len(s) == 10:
        digits = country_code + s[1:]
    elif len(s) == 9 and s[0] in "17":
        digits = country_code + s
    else:
        return ""
    if not digits.isdigit() or not 10 <= len(digits) <= 15:
        return ""
    if digits.startswith("254") and (len(digits) != 12 or digits[3] not in "17"):
        return ""
    return "+" + digits


def clip(text):
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 3].rstrip() + "..."


def send_bulk(numbers, message):
    """Send one message to many numbers. Returns {number: (status, detail)} where
    status is "sent", "failed" or "not_configured"."""
    numbers = [n for n in dict.fromkeys(numbers) if n]
    message = clip(message)
    if not numbers:
        return {}
    p = provider()
    if p == "":
        return {n: ("not_configured", "No SMS provider is set up.") for n in numbers}
    if p == "console":
        for n in numbers:
            print(f"[DEV SMS] to {n}: {message}")
        return {n: ("sent", "console") for n in numbers}
    out = {}
    for i in range(0, len(numbers), BATCH):
        out.update(_africastalking(numbers[i:i + BATCH], message))
    return out


def send_one(number, message):
    n = normalize_phone(number)
    if not n:
        return "failed", "Not a valid phone number."
    return send_bulk([n], message).get(n, ("failed", "No response."))


def _africastalking(numbers, message):
    username = os.environ["DJANGO_AT_USERNAME"]
    form = {"username": username, "to": ",".join(numbers), "message": message}
    sender = os.environ.get("DJANGO_AT_SENDER_ID", "").strip()
    if sender:
        form["from"] = sender
    req = urllib.request.Request(
        SANDBOX_URL if username == "sandbox" else LIVE_URL,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={"apiKey": os.environ["DJANGO_AT_API_KEY"], "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "marian-backend/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:150].decode("utf-8", "replace")
        log.warning("SMS provider rejected batch: HTTP %s", exc.code)
        return {n: ("failed", f"Provider error {exc.code}: {detail}"[:200]) for n in numbers}
    except Exception as exc:  # network, timeout, bad JSON
        log.warning("SMS provider unreachable: %s", type(exc).__name__)
        return {n: ("failed", "SMS provider could not be reached.") for n in numbers}
    out = {n: ("failed", "Not accepted by the provider.") for n in numbers}
    for r in (data.get("SMSMessageData") or {}).get("Recipients") or []:
        num = r.get("number")
        if num not in out:
            continue
        ok = int(r.get("statusCode") or 0) in _OK_CODES
        out[num] = ("sent", r.get("cost", "")) if ok else ("failed", str(r.get("status") or "Rejected")[:200])
    return out
