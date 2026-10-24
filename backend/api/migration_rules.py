"""Student migration rules: pure logic, no database access.

Nothing here saves anything. It reads an uploaded table, checks it, places each
learner in a real class, sorts the list and says what still needs a person.

Row severities:
  block   - cannot be imported until the file is corrected
  confirm - blocked until the uploader confirms it (shown in red)
  notice  - shown for information, no action needed
"""
import difflib
import re
from collections import defaultdict

PROVISIONAL_PREFIX = "NO-ADM-"
UNREADABLE = "[UNREADABLE]"
CHECK_OPEN = "[CHECK:"
_LABELS = {"first_name": "First name", "last_name": "Surname", "full_name": "Name", "other_names": "Other names",
           "admission_number": "Admission number", "assessment_number": "Assessment number", "upi": "UPI",
           "class_level": "Class", "stream": "Stream"}
ID_FIELDS = ("admission_number", "assessment_number", "upi")

ALIASES = {
    "admission_number": ["admission number", "admission no", "admission", "adm no", "adm", "adm number", "admno", "admission num"],
    "assessment_number": ["assessment number", "assessment no", "assessment", "assess no", "assess number", "assessment num"],
    "upi": ["upi", "upi no", "upi number", "nemis upi", "nemis no", "nemis number", "unique personal identifier"],
    "first_name": ["first name", "firstname", "given name", "given names", "forename"],
    "last_name": ["last name", "lastname", "surname", "family name"],
    "other_names": ["other names", "other name", "middle name", "middle names"],
    "full_name": ["name", "names", "full name", "full names", "student name", "learner name", "pupil name", "learner", "student"],
    "class_level": ["class", "class level", "grade", "level", "form", "current class", "current grade", "class grade"],
    "stream": ["stream", "arm", "section"],
}
_ALIAS = {alias: canon for canon, names in ALIASES.items() for alias in names}


def _k(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _cell(value):
    return "" if value is None else str(value).strip()


def _idkey(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def natural_key(value):
    parts = re.split(r"(\d+)", str(value or "").casefold())
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts if p != ""]


def name_key(first, last):
    return " ".join(sorted(_k(f"{first} {last}").split()))


def is_senior_level(name):
    n = _k(name)
    return bool(re.search(r"\bgrade 0*(10|11|12)\b", n) or re.fullmatch(r"0*(10|11|12)", n))


def is_provisional(admission):
    return str(admission or "").upper().startswith(PROVISIONAL_PREFIX)


def detect_header_row(matrix, scan=15):
    best, best_hits = None, 1
    for i, row in enumerate(matrix[:scan]):
        hits = sum(1 for c in row if _k(c) in _ALIAS)
        if hits > best_hits:
            best, best_hits = i, hits
    return best


def _issue(code, severity, message, field=""):
    return {"code": code, "severity": severity, "message": message, "field": field}


def match_class(text, stream_text, levels):
    """Return (level, stream, notices, error). Never guesses."""
    notices = []
    t, st = _k(text), _k(stream_text)
    if not t:
        return None, None, notices, ("class_missing", "No class or grade is given for this learner.")
    exact = [l for l in levels if _k(l["name"]) == t]
    level, rest = None, ""
    if len(exact) > 1:
        return None, None, notices, ("class_ambiguous", f"'{text}' matches more than one class in this school.")
    if len(exact) == 1:
        level = exact[0]
    else:
        cands = []
        for l in levels:
            lk = _k(l["name"])
            if t.startswith(lk) and len(t) > len(lk):
                if lk[-1:].isdigit() and t[len(lk)].isdigit():
                    continue
                remainder = t[len(lk):].strip()
                if remainder and any(_k(s["name"]) == remainder for s in l["streams"]):
                    cands.append((l, remainder))
        if len(cands) == 1:
            level, rest = cands[0]
            notices.append(_issue("class_split", "notice", f"Read '{text}' as {level['name']} + stream {rest.upper()}.", "class_level"))
        elif len(cands) > 1:
            return None, None, notices, ("class_ambiguous", f"'{text}' matches more than one class in this school.")
        elif t.isdigit():
            nums = [l for l in levels if _k(l["name"]).split()[-1:] == [str(int(t))]]
            if len(nums) == 1:
                level = nums[0]
                notices.append(_issue("class_number_read", "notice", f"Read '{text}' as {level['name']}.", "class_level"))
            elif len(nums) > 1:
                return None, None, notices, ("class_ambiguous", f"'{text}' matches more than one class in this school.")
    if level is None:
        close = difflib.get_close_matches(t, [_k(l["name"]) for l in levels], n=3, cutoff=0.5)
        names = [l["name"] for l in levels if _k(l["name"]) in close]
        hint = f" Closest in this school: {', '.join(names)}." if names else ""
        return None, None, notices, ("class_not_found", f"Class '{text}' does not exist in this school.{hint}")
    if rest and st and rest != st:
        return None, None, notices, ("class_conflict", f"'{text}' and stream '{stream_text}' do not agree.")
    wanted = st or rest
    stream = None
    if wanted:
        stream = next((s for s in level["streams"] if _k(s["name"]) == wanted), None)
        if stream is None:
            have = ", ".join(s["name"] for s in level["streams"]) or "none"
            return None, None, notices, ("stream_not_found", f"Stream '{stream_text or rest}' does not exist in {level['name']}. Streams there: {have}.")
    elif level["streams"]:
        notices.append(_issue("no_stream", "notice", f"No stream given; placed in {level['name']} without a stream.", "stream"))
    return level, stream, notices, None


def _split_full_name(value, order):
    tokens = str(value or "").split()
    if len(tokens) < 2:
        return "", ""
    if order == "last_first":
        return " ".join(tokens[1:]), tokens[0]
    return " ".join(tokens[:-1]), tokens[-1]


def analyse_upload(matrix, structure, existing=(), source="digital", name_order=None,
                   default_class="", confirmations=None, provisional_start=1, fixes=None):
    """Check an uploaded table. `matrix` is a list of rows (list of cells).
    `structure` is the school's real classes: [{id, name, level_number, streams:[{id, name}]}].
    `existing` are students already in Marian. `source` is 'digital' or 'paper'.
    `confirmations` is {row_number: [codes]} or {'all': [codes]}.
    """
    confirmations = confirmations or {}
    fixes = fixes or {}
    out = {"file_issues": [], "needs_input": [], "rows": [], "sorted_by": "", "summary": {},
           "senior_levels": [l["name"] for l in structure if is_senior_level(l["name"])]}
    head = detect_header_row(matrix)
    if head is None:
        out["file_issues"].append(_issue("no_header", "block", "No header row was found. The first rows should name the columns, for example Admission No, Name, Class."))
        return out
    cols = defaultdict(list)
    for idx, cell in enumerate(matrix[head]):
        canon = _ALIAS.get(_k(cell))
        if canon:
            cols[canon].append((idx, _cell(cell)))
    for canon, found in cols.items():
        if len(found) > 1:
            names = ", ".join(f"'{n}'" for _, n in found)
            out["file_issues"].append(_issue("ambiguous_columns", "block", f"More than one column could be {canon.replace('_', ' ')}: {names}. Remove or rename the extra one."))
    if head > 0:
        out["file_issues"].append(_issue("header_row", "notice", f"Skipped {head} row(s) above the column names."))
    has_split = "first_name" in cols and "last_name" in cols
    if not has_split and "full_name" not in cols:
        out["file_issues"].append(_issue("no_name_columns", "block", "No name columns were found. Use First name + Surname, or one Name column."))
    if "class_level" not in cols and not default_class:
        out["file_issues"].append(_issue("no_class_column", "block", "No Class or Grade column was found. Add one, or choose one class for the whole file."))
    if any(i["severity"] == "block" for i in out["file_issues"]):
        return out
    if "other_names" in cols and has_split:
        out["file_issues"].append(_issue("other_names", "notice", "The 'Other names' column is added after First name. It is not treated as a surname."))
    body = [(i + 1, row) for i, row in enumerate(matrix) if i > head and any(_cell(c) for c in row)]

    fx = {}

    def raw_value(row, canon):
        if canon in fx:
            return _cell(fx[canon])
        found = cols.get(canon)
        if not found or found[0][0] >= len(row):
            return ""
        return _cell(row[found[0][0]])

    def get(row, canon):
        v = raw_value(row, canon)
        if UNREADABLE in v:
            return ""
        if v.startswith(CHECK_OPEN):
            v = v[len(CHECK_OPEN):]
            return (v[:-1] if v.endswith("]") else v).strip()
        return v

    if not has_split and name_order not in ("first_last", "last_first"):
        sample = [get(r, "full_name") for _, r in body[:3]]
        out["needs_input"].append({"code": "name_order", "message": "Your file has one Name column. Say which name comes first.", "sample": sample, "choices": ["first_last", "last_first"]})
        return out
    if default_class and "class_level" not in cols:
        out["file_issues"].append(_issue("default_class", "notice", f"Every learner is placed in {default_class}, as chosen for the whole file."))

    rows = []
    for number, raw in body:
        fx.clear()
        fx.update(fixes.get(number) or {})
        if has_split:
            first = (get(raw, "first_name") + " " + get(raw, "other_names")).strip()
            last = get(raw, "last_name")
        else:
            first, last = _split_full_name(get(raw, "full_name"), name_order)
        r = {"row": number, "first_name": first, "last_name": last, "admission_number": get(raw, "admission_number"),
             "assessment_number": get(raw, "assessment_number"), "upi": get(raw, "upi"), "issues": [],
             "level": None, "stream": None, "provisional_admission": False}
        if not has_split and len((get(raw, "full_name")).split()) > 2:
            r["issues"].append(_issue("name_split", "notice", f"Name split as first: '{first}', surname: '{last}'.", "name"))
        for _f in ("first_name", "last_name"):
            if _f in fx:
                r[_f] = _cell(fx[_f])
        for _canon in cols:
            _v = raw_value(raw, _canon)
            _name = _LABELS.get(_canon, _canon.replace("_", " ").capitalize())
            if UNREADABLE in _v:
                r["issues"].append(_issue("unreadable_cell", "block", f"{_name} could not be read from the photo. Look at the page and type it.", _canon))
            elif _v.startswith(CHECK_OPEN):
                r["issues"].append(_issue("check_reading_" + _canon, "confirm", f'{_name} was hard to read. It was read as "{get(raw, _canon)}". Check it against the page.', _canon))
        r["class_text"] = get(raw, "class_level") or default_class
        r["stream_text"] = get(raw, "stream")
        rows.append(r)

    ex_adm = {_idkey(s.get("admission_number")): s for s in existing if _idkey(s.get("admission_number"))}
    ex_ass = {_idkey(s.get("assessment_number")): s for s in existing if _idkey(s.get("assessment_number"))}
    ex_upi = {_idkey(s.get("upi")): s for s in existing if _idkey(s.get("upi"))}
    ex_names = defaultdict(list)
    for s in existing:
        ex_names[name_key(s.get("first_name"), s.get("last_name"))].append(s)

    groups = {f: defaultdict(list) for f in ID_FIELDS}
    names = defaultdict(list)
    for r in rows:
        for f in ID_FIELDS:
            if _idkey(r[f]):
                groups[f][_idkey(r[f])].append(r)
        if r["first_name"] and r["last_name"]:
            names[name_key(r["first_name"], r["last_name"])].append(r)

    label = {"admission_number": "Admission number", "assessment_number": "Assessment number", "upi": "UPI"}
    exmap = {"admission_number": ex_adm, "assessment_number": ex_ass, "upi": ex_upi}
    for r in rows:
        if not r["first_name"] or not r["last_name"]:
            r["issues"].append(_issue("name_missing", "block", "First name and surname are both required.", "name"))
        if len(r["first_name"]) > 100 or len(r["last_name"]) > 100:
            r["issues"].append(_issue("name_too_long", "block", "A name is longer than 100 characters. Correct it, it will not be cut short.", "name"))
        if len(r["admission_number"]) > 50:
            r["issues"].append(_issue("admission_too_long", "block", "Admission number is longer than 50 characters.", "admission_number"))
        for f in ID_FIELDS:
            key = _idkey(r[f])
            if not key:
                continue
            same = groups[f][key]
            if len(same) > 1:
                others = ", ".join(str(o["row"]) for o in same if o is not r)
                r["issues"].append(_issue(f"duplicate_{f}", "block", f"{label[f]} {r[f]} is also on row {others}. Each learner needs their own.", f))
            if key in exmap[f]:
                s = exmap[f][key]
                who = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
                r["issues"].append(_issue(f"{f}_exists", "block", f"{label[f]} {r[f]} already belongs to {who} in Marian.", f))
        if not r["admission_number"]:
            r["issues"].append(_issue("missing_admission", "confirm", "ADMISSION NUMBER MISSING. If you confirm, this learner gets a temporary number (NO-ADM-0001...) marked in red until the real number is entered.", "admission_number"))
        if r["first_name"] and r["last_name"]:
            nk = name_key(r["first_name"], r["last_name"])
            for o in names[nk]:
                if o is not r and not (_idkey(r["admission_number"]) and _idkey(r["admission_number"]) == _idkey(o["admission_number"])):
                    r["issues"].append(_issue("same_name", "confirm", f"SAME NAME as row {o['row']} (admission {o['admission_number'] or 'none'}). Confirm they are different learners.", "name"))
            for s in ex_names.get(nk, []):
                if _idkey(r["admission_number"]) != _idkey(s.get("admission_number")):
                    r["issues"].append(_issue("same_name_existing", "confirm", f"SAME NAME as {s.get('admission_number') or 'a learner'} already in Marian. Confirm they are different learners.", "name"))
            if source == "paper":
                for ok, others in list(names.items()) + list(ex_names.items()):
                    if ok != nk and abs(len(ok) - len(nk)) <= 2 and difflib.SequenceMatcher(None, nk, ok).ratio() >= 0.9:
                        r["issues"].append(_issue("similar_name", "confirm", "HANDWRITTEN NAME looks very close to another learner's. Check the spelling, then confirm they are different.", "name"))
                        break
        level, stream, notices, error = match_class(r["class_text"], r["stream_text"], structure)
        r["issues"].extend(notices)
        if error:
            r["issues"].append(_issue(error[0], "block", error[1], "class_level"))
        else:
            r["level"], r["stream"] = level, stream
            if is_senior_level(level["name"]) and not r["assessment_number"]:
                r["issues"].append(_issue("assessment_missing", "block", f"{level['name']} learners must have an assessment number.", "assessment_number"))

    placed = [r for r in rows if r["level"]]
    for f in ID_FIELDS:
        if placed and sum(1 for r in placed if r[f]) / len(placed) >= 0.8:
            out["sorted_by"] = f
            break
    else:
        out["sorted_by"] = "name"

    def sort_key(r):
        if not r["level"]:
            return (1, 0, [], [], [], r["row"])
        ident = r[out["sorted_by"]] if out["sorted_by"] != "name" else f"{r['last_name']} {r['first_name']}"
        return (0, r["level"]["level_number"], natural_key(r["level"]["name"]),
                natural_key(r["stream"]["name"]) if r["stream"] else [], [(0, 1, "")] if not ident else natural_key(ident), r["row"])

    rows.sort(key=sort_key)
    used = {_idkey(r["admission_number"]) for r in rows} | set(ex_adm)
    n = provisional_start
    for r in rows:
        given = set(confirmations.get(r["row"], [])) | set(confirmations.get("all", []))
        blocks = [i for i in r["issues"] if i["severity"] == "block"]
        pending = [i for i in r["issues"] if i["severity"] == "confirm" and i["code"] not in given]
        r["status"] = "blocked" if blocks else ("needs_confirmation" if pending else "ready")
        if r["status"] == "ready" and "missing_admission" in given and not r["admission_number"]:
            while _idkey(f"{PROVISIONAL_PREFIX}{n:04d}") in used:
                n += 1
            r["admission_number"] = f"{PROVISIONAL_PREFIX}{n:04d}"
            used.add(_idkey(r["admission_number"]))
            r["provisional_admission"] = True
        r["class_label"] = (r["level"]["name"] + (f" {r['stream']['name']}" if r["stream"] else "")) if r["level"] else ""
        r["level_id"] = r["level"]["id"] if r["level"] else None
        r["stream_id"] = r["stream"]["id"] if r["stream"] else None
    by_class = defaultdict(int)
    for r in rows:
        if r["class_label"]:
            by_class[r["class_label"]] += 1
    out["rows"] = rows
    out["summary"] = {"total": len(rows), "ready": sum(r["status"] == "ready" for r in rows),
                      "needs_confirmation": sum(r["status"] == "needs_confirmation" for r in rows),
                      "blocked": sum(r["status"] == "blocked" for r in rows),
                      "temporary_admission": sum(r["provisional_admission"] for r in rows), "by_class": dict(by_class)}
    return out
