"""Student migration rules: pure logic, no database access.

Nothing here saves anything. It reads an uploaded table, checks it, places each
learner in a real class, sorts the list and says what still needs a person.

Row outcomes:
  ready              - will be added
  needs_confirmation - added once the uploader says the row is correct
  blocked            - cannot be added until the row is corrected
  duplicate          - already in Marian, so it is skipped (not an error)
"""
import difflib
import re
from collections import defaultdict

PROVISIONAL_PREFIX = "NO-ADM-"
UNREADABLE = "[UNREADABLE]"
CHECK_OPEN = "[CHECK:"

FIELD_LABELS = {
    "first_name": "First name",
    "last_name": "Surname",
    "full_name": "Full name",
    "other_names": "Other names",
    "admission_number": "Admission number",
    "assessment_number": "Assessment number",
    "upi": "UPI",
    "class_level": "Class",
    "stream": "Stream",
}
FIELD_ORDER = ("first_name", "last_name", "full_name", "other_names",
               "admission_number", "assessment_number", "upi", "class_level", "stream")
ID_FIELDS = ("admission_number", "assessment_number", "upi")

ALIASES = {
    "admission_number": [
        "admission number", "admission no", "admission", "adm no", "adm number", "adm",
        "admno", "admission num", "registration number", "registration no", "reg no",
        "reg number", "student number", "student id", "learner number", "learner id",
        "student admission number", "admission number of learner",
        "namba ya kuingia", "nambari ya kuingia", "namba ya usajili", "nambari ya usajili",
        "namba ya mwanafunzi", "nambari ya mwanafunzi", "namba ya kutambulisha",
    ],
    "assessment_number": [
        "assessment number", "assessment no", "assessment", "assess no", "assess number",
        "assessment num", "candidate number", "candidate no",
        "namba ya mtihani", "nambari ya mtihani",
    ],
    "upi": [
        "upi", "upi no", "upi number", "nemis upi", "nemis no", "nemis number",
        "unique personal identifier", "unique identifier", "upi nemis",
    ],
    "first_name": ["first name", "firstname", "given name", "given names", "forename", "first",
                   "jina la kwanza", "jina la kati"],
    "last_name": ["last name", "lastname", "surname", "sur name", "family name", "family", "last",
                  "jina la ukoo", "jina la mwisho"],
    "other_names": ["other names", "other name", "middle name", "middle names", "middle"],
    "full_name": [
        "name", "names", "full name", "full names", "student name", "learner name",
        "pupil name", "learner", "student", "learners name", "students name",
        "learner s name", "student s name", "pupil s name", "name of learner",
        "name of student", "name of the learner", "name of the student",
        "jina kamili", "jina", "majina", "jina la mwanafunzi", "jina la mwanafunzi kamili",
    ],
    "class_level": [
        "class", "class level", "grade", "level", "form", "current class", "current grade",
        "class grade", "class grade", "class stream", "grade stream", "class and stream",
        "grade and class", "standard", "std", "class or grade", "grade or class",
        "darasa", "gredi", "kidato", "darasa la sasa",
    ],
    "stream": ["stream", "arm", "section", "class arm", "stream arm", "mkondo"],
}
_ALIAS = {alias: canon for canon, names in ALIASES.items() for alias in names}

# Words too generic to match inside a longer heading.
_WEAK = {"name", "names", "learner", "student", "pupil", "class", "grade", "stream",
         "level", "form", "first", "last", "family", "middle", "adm", "upi",
         "jina", "majina", "darasa", "gredi", "kidato", "mkondo"}


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


def _issue(code, severity, message, field=""):
    return {"code": code, "severity": severity, "message": message, "field": field}


# --------------------------------------------------------------------------
# Header and column recognition
# --------------------------------------------------------------------------
def guess_field(label):
    """Return (field, confidence) for one heading. Never raises."""
    k = _k(label)
    if not k:
        return None, None
    if k in _ALIAS:
        return _ALIAS[k], "exact"
    close = difflib.get_close_matches(k, list(_ALIAS), n=1, cutoff=0.87)
    if close:
        return _ALIAS[close[0]], "likely"
    for alias in sorted(_ALIAS, key=len, reverse=True):
        if alias in _WEAK or " " not in alias or len(alias) < 9:
            continue
        if alias in k:
            return _ALIAS[alias], "likely"
    return None, None


def detect_header_row(matrix, scan=15):
    best, best_hits = None, 1
    for i, row in enumerate(matrix[:scan]):
        hits = sum(1 for c in row if _k(c) in _ALIAS)
        if hits > best_hits:
            best, best_hits = i, hits
    return best


_NUMBERISH = re.compile(r"^[\s\d.,/:\-]+$")


def _guess_header_row(matrix, scan=10):
    """Find a heading row when none of the headings are recognised.

    A heading row holds short words, no bare numbers, and is followed by a wider
    or equally wide row of data. Anything else is treated as data, not headings.
    """
    for i, row in enumerate(matrix[:scan]):
        cells = [_cell(c) for c in row]
        filled = [c for c in cells if c]
        if len(filled) < 2:
            continue
        if any(_NUMBERISH.match(c) for c in filled):
            continue
        if not any(re.search(r"[A-Za-z]", c) for c in filled):
            continue
        if max(len(c) for c in filled) > 40:
            continue
        below = next((r for r in matrix[i + 1:i + 4] if any(_cell(c) for c in r)), None)
        if below is None:
            continue
        if sum(1 for c in below if _cell(c)) < len(filled) - 1:
            continue
        return i
    return None


def _header_index(matrix, header_row):
    """Return the heading row index, -1 for 'no headings', or None if unknown."""
    if header_row is not None:
        if header_row == -1:
            return -1
        if isinstance(header_row, int) and 0 <= header_row < len(matrix):
            return header_row
        return None
    head = detect_header_row(matrix)
    if head is not None:
        return head
    return _guess_header_row(matrix)


def resolve_columns(header_cells, mapping=None):
    """Work out which column holds which field.

    `mapping` is {field: column_index} and always wins over detection, so an
    administrator can correct a heading the rules did not recognise.
    """
    mapping = mapping or {}
    columns = []
    for idx, raw in enumerate(header_cells):
        label = _cell(raw)
        field, confidence = guess_field(label)
        columns.append({"index": idx, "label": label, "field": field,
                        "confidence": confidence if field else None})
    for field, idx in mapping.items():
        if field not in FIELD_LABELS:
            continue
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(header_cells):
            continue
        for col in columns:
            if col["index"] == idx:
                col["field"] = field
                col["confidence"] = "manual"
            elif col["field"] == field:
                col["field"] = None
                col["confidence"] = None
    cols = defaultdict(list)
    unknown = []
    for col in columns:
        if col["field"]:
            cols[col["field"]].append((col["index"], col["label"]))
        elif col["label"]:
            unknown.append({"index": col["index"], "label": col["label"]})
    return cols, columns, unknown


# --------------------------------------------------------------------------
# Class and stream matching
# --------------------------------------------------------------------------
def suggest_classes(text, levels, limit=4):
    """Class names that look close to `text`, for the correction picker."""
    if not levels:
        return []
    t = _k(text)
    if not t:
        return [l["name"] for l in levels[:limit]]
    close = difflib.get_close_matches(t, [_k(l["name"]) for l in levels], n=limit, cutoff=0.45)
    names = [l["name"] for l in levels if _k(l["name"]) in close]
    numbers = re.findall(r"\d+", t)
    if numbers:
        for l in levels:
            if l["name"] not in names and re.findall(r"\d+", _k(l["name"]))[-1:] == [str(int(numbers[0]))]:
                names.append(l["name"])
    return names[:limit]


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
        m = re.match(r"^(form|frm|f|grade|gr|g|class|std|standard|year|yr|y|level|s)?\s*0*(\d{1,2})\s*[-_/.]?\s*(.*)$", t)
        if m:
            pref, num, tail = m.groups()
            nums = []
            for l in levels:
                tail_num = re.search(r"(\d+)\s*$", l["name"])
                if tail_num and int(tail_num.group(1)) == int(num):
                    nums.append(l)
            if pref and len(nums) > 1:
                same = [l for l in nums if _k(l["name"]).startswith(pref[0])]
                if same:
                    nums = same
            if len(nums) == 1:
                level, rest = nums[0], tail.strip()
                notices.append(_issue("class_short_read", "notice", f"Read '{text}' as {level['name']}" + (f" stream {rest.upper()}" if rest else "") + ".", "class_level"))
            elif len(nums) > 1:
                return None, None, notices, ("class_ambiguous", f"'{text}' matches more than one class in this school: " + ", ".join(l["name"] for l in nums) + ". Write the full class name.")
    if level is None:
        close = difflib.get_close_matches(t, [_k(l["name"]) for l in levels], n=3, cutoff=0.5)
        names = [l["name"] for l in levels if _k(l["name"]) in close]
        if names:
            hint = f" Closest in this school: {', '.join(names)}."
        elif levels:
            hint = f" Classes in this school: {', '.join(l['name'] for l in levels)}."
        else:
            hint = " This school has no classes yet. Add them in Setup."
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


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------
def analyse_upload(matrix, structure, existing=(), source="digital", name_order=None,
                   default_class="", confirmations=None, provisional_start=1, fixes=None,
                   mapping=None, header_row=None):
    """Check an uploaded table. `matrix` is a list of rows (list of cells).

    `structure` is the school's real classes: [{id, name, level_number, streams:[{id, name}]}].
    `existing` are students already in Marian. `source` is 'digital' or 'paper'.
    `confirmations` is {row_number: [codes]} or {'all': [codes]}.
    `fixes` is {row_number: {field: value}}.
    `mapping` is {field: column_index} for headings the rules did not recognise.
    """
    confirmations = confirmations or {}
    fixes = fixes or {}
    mapping = mapping or {}
    out = {"file_issues": [], "needs_input": [], "rows": [], "sorted_by": "", "summary": {},
           "senior_levels": [l["name"] for l in structure if is_senior_level(l["name"])],
           "classes": [{"id": l["id"], "name": l["name"], "level_number": l["level_number"],
                        "streams": [{"id": s["id"], "name": s["name"]} for s in l["streams"]]}
                       for l in structure],
           "headers": [], "columns": [], "mapping": {}, "unknown_columns": [],
           "mapping_uncertain": False, "row_count": 0, "header_row": None}
    if not matrix:
        out["file_issues"].append(_issue("empty_file", "block", "The file has no rows."))
        return out

    head = _header_index(matrix, header_row)
    if head is None:
        out["file_issues"].append(_issue(
            "no_header", "block",
            "No column names were found. The first rows should name the columns, for example "
            "Admission number, First name, Surname, Class."))
        return out

    if head == -1:
        width = max((len(r) for r in matrix[:5]), default=0)
        header_cells = [f"Column {i + 1}" for i in range(width)]
        body_rows = matrix
        out["header_row"] = -1
    else:
        header_cells = [_cell(c) for c in matrix[head]]
        body_rows = matrix[head + 1:]
        out["header_row"] = head
        if head > 0:
            out["file_issues"].append(_issue("header_row", "notice", f"Skipped {head} row(s) above the column names."))

    cols, columns, unknown = resolve_columns(header_cells, mapping)
    out["headers"] = [c["label"] for c in columns]
    out["unknown_columns"] = unknown
    out["mapping"] = {field: found[0][0] for field, found in cols.items()}

    offset = 1 if head == -1 else head + 2
    body = [(i + offset, row) for i, row in enumerate(body_rows) if any(_cell(c) for c in row)]
    for col in columns:
        samples = []
        for _, row in body[:60]:
            if col["index"] < len(row):
                value = _cell(row[col["index"]])
                if value and value not in samples:
                    samples.append(value)
            if len(samples) >= 3:
                break
        col["samples"] = samples
    out["columns"] = columns
    out["row_count"] = len(body)

    for field, found in cols.items():
        if len(found) > 1:
            names = ", ".join(f"'{n}'" for _, n in found)
            out["file_issues"].append(_issue(
                "ambiguous_columns", "block",
                f"More than one column could be {FIELD_LABELS.get(field, field).lower()}: {names}. "
                "Remove or rename the extra one, or choose the column to use below."))
    has_split = "first_name" in cols and "last_name" in cols
    has_full = "full_name" in cols
    name_ready = has_split or has_full
    has_class = "class_level" in cols

    out["mapping_uncertain"] = bool(
        not name_ready
        or any(c["confidence"] == "likely" for c in columns))

    if not name_ready:
        out["needs_input"].append({
            "code": "mapping",
            "message": "We could not tell which column holds the learner's name.",
            "missing": ["name"],
            "fields": [f for f in ("first_name", "last_name", "full_name", "other_names",
                                   "admission_number", "assessment_number", "upi",
                                   "class_level", "stream")],
            "mapping": out["mapping"],
        })
        return out

    if any(i["severity"] == "block" for i in out["file_issues"]):
        return out
    if has_full and has_split:
        out["file_issues"].append(_issue(
            "full_name_ignored", "notice",
            "The single Name column was ignored because First name and Surname columns are present."))
    if "other_names" in cols and has_split:
        out["file_issues"].append(_issue(
            "other_names", "notice",
            "The 'Other names' column is added after First name. It is not treated as a surname."))
    if unknown:
        names = ", ".join(u["label"] for u in unknown[:6])
        more = f" and {len(unknown) - 6} more" if len(unknown) > 6 else ""
        out["file_issues"].append(_issue(
            "ignored_columns", "notice",
            f"These columns were not imported: {names}{more}. Choose a column above if one of them belongs to a field."))

    if not has_class and not default_class:
        out["file_issues"].append(_issue(
            "no_class_column", "notice",
            "This file has no class column. Choose the class that these learners belong to, "
            "and every row is placed in it."))

    if not has_split and name_order not in ("first_last", "last_first"):
        sample = []
        for _, row in body[:3]:
            if "full_name" in cols and cols["full_name"][0][0] < len(row):
                value = _cell(row[cols["full_name"][0][0]])
                if value and value != UNREADABLE and not value.startswith(CHECK_OPEN):
                    sample.append(value)
        out["needs_input"].append({
            "code": "name_order",
            "message": "Your file has one Name column. Say which name comes first.",
            "sample": sample, "choices": ["first_last", "last_first"]})
        return out

    # A class chosen for the whole file is resolved once, against real classes.
    default_level = default_stream = None
    if default_class:
        default_level, default_stream, _n, err = match_class(default_class, "", structure)
        if err:
            out["file_issues"].append(_issue(
                "default_class_invalid", "block",
                f"The class chosen for the whole file, '{default_class}', does not exist in this school. "
                "Choose one of the classes already in Setup.", "class_level"))
            return out
        if "class_level" not in cols:
            label = default_level["name"] + (f" {default_stream['name']}" if default_stream else "")
            out["file_issues"].append(_issue(
                "default_class", "notice",
                f"No class column in this file, so every learner is placed in {label}, as you chose."))

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

    rows = []
    for number, raw in body:
        fx.clear()
        fx.update(fixes.get(number) or {})
        if has_split:
            first = (get(raw, "first_name") + " " + get(raw, "other_names")).strip()
            last = get(raw, "last_name")
        else:
            first, last = _split_full_name(get(raw, "full_name"), name_order)
        r = {"row": number, "first_name": first, "last_name": last,
             "admission_number": get(raw, "admission_number"),
             "assessment_number": get(raw, "assessment_number"), "upi": get(raw, "upi"),
             "issues": [], "suggestions": {}, "level": None, "stream": None,
             "provisional_admission": False, "corrected": bool(fx)}
        if not has_split and len((get(raw, "full_name")).split()) > 2:
            r["issues"].append(_issue("name_split", "notice", f"Name split as first: '{first}', surname: '{last}'.", "name"))
        for _f in ("first_name", "last_name"):
            if _f in fx:
                r[_f] = _cell(fx[_f])
        for _canon in cols:
            _v = raw_value(raw, _canon)
            _name = FIELD_LABELS.get(_canon, _canon.replace("_", " ").capitalize())
            if UNREADABLE in _v:
                r["issues"].append(_issue("unreadable_cell", "block", f"{_name} could not be read from the photo. Look at the page and type it.", _canon))
            elif _v.startswith(CHECK_OPEN):
                r["issues"].append(_issue("check_reading_" + _canon, "confirm", f'{_name} was hard to read. It was read as "{get(raw, _canon)}". Check it against the page.', _canon))
        r["class_text"] = get(raw, "class_level")
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
                r["duplicate"] = f"{label[f]} {r[f]} is already in Marian" + (f" ({who})" if who else "")
                r["issues"].append(_issue(
                    f"{f}_exists", "notice",
                    f"{label[f]} {r[f]} is already in Marian" + (f" as {who}" if who else "")
                    + ". This row will be skipped so the learner is not added twice.", f))
        if not r["admission_number"]:
            r["issues"].append(_issue("missing_admission", "confirm", "No admission number. If you confirm, this learner gets a temporary number (NO-ADM-0001...) marked until the real number is entered.", "admission_number"))
        if r["first_name"] and r["last_name"]:
            nk = name_key(r["first_name"], r["last_name"])
            for o in names[nk]:
                if o is not r and not (_idkey(r["admission_number"]) and _idkey(r["admission_number"]) == _idkey(o["admission_number"])):
                    r["issues"].append(_issue("same_name", "confirm", f"Same name as row {o['row']} (admission {o['admission_number'] or 'none'}). Confirm they are different learners.", "name"))
            for s in ex_names.get(nk, []):
                if _idkey(r["admission_number"]) != _idkey(s.get("admission_number")):
                    who = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
                    if not r["admission_number"] and not r.get("duplicate"):
                        # The file gives no admission number and Marian already has a
                        # learner by this name. Running the same import twice would add
                        # a second copy under a new temporary number, so skip it.
                        r["duplicate"] = f"Already in Marian as {who} ({s.get('admission_number') or 'no number'})"
                        r["issues"].append(_issue(
                            "same_name_existing", "notice",
                            f"Already in Marian as {who} ({s.get('admission_number') or 'no number'})"
                            ". Your file has no admission number for this learner, so the row is skipped "
                            "to avoid adding them twice. Add the admission number if this is someone else.", "name"))
                    else:
                        r["issues"].append(_issue("same_name_existing", "confirm", f"Same name as {who} ({s.get('admission_number') or 'no number'}) already in Marian. Confirm they are different learners.", "name"))
            if source == "paper":
                for ok, others in list(names.items()) + list(ex_names.items()):
                    if ok != nk and abs(len(ok) - len(nk)) <= 2 and difflib.SequenceMatcher(None, nk, ok).ratio() >= 0.9:
                        r["issues"].append(_issue("similar_name", "confirm", "Handwritten name looks very close to another learner's. Check the spelling, then confirm they are different.", "name"))
                        break

        if default_level is not None and not r["class_text"].strip():
            r["level"], r["stream"] = default_level, default_stream
            r["class_text"] = default_level["name"] + (f" {default_stream['name']}" if default_stream else "")
            r["issues"].append(_issue(
                "default_class_used", "notice",
                f"No class in this row; placed in {r['class_text']} as you chose for the whole file.", "class_level"))
        else:
            level, stream, notices, error = match_class(r["class_text"], r["stream_text"], structure)
            r["issues"].extend(notices)
            if error:
                r["issues"].append(_issue(error[0], "block", error[1], "class_level"))
                if error[0] in ("class_not_found", "class_ambiguous", "class_short_read", "class_missing"):
                    r["suggestions"]["class_level"] = suggest_classes(r["class_text"], structure)
                if error[0] in ("stream_not_found", "class_conflict", "class_ambiguous"):
                    level_guess = next((l for l in structure if _k(l["name"]) == _k(r["class_text"])), None)
                    if level_guess:
                        r["suggestions"]["stream"] = [s["name"] for s in level_guess["streams"]]
            else:
                r["level"], r["stream"] = level, stream

        if r["level"] and is_senior_level(r["level"]["name"]) and not r["assessment_number"]:
            r["issues"].append(_issue(
                "assessment_missing", "block",
                f"{r['level']['name']} learners must have an assessment number: it is needed for "
                "registration and for exams. Add it here, or in your file.", "assessment_number"))
        if r.get("duplicate"):
            r["issues"].append(_issue("duplicate_row", "notice", "Already in Marian, so this row is skipped. Change the admission number if it is a different learner.", "admission_number"))

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
                natural_key(r["stream"]["name"]) if r["stream"] else [],
                [(0, 1, "")] if not ident else natural_key(ident), r["row"])

    rows.sort(key=sort_key)
    used = {_idkey(r["admission_number"]) for r in rows} | set(ex_adm)
    n = provisional_start
    for r in rows:
        given = set(confirmations.get(r["row"], [])) | set(confirmations.get("all", []))
        blocks = [i for i in r["issues"] if i["severity"] == "block"]
        pending = [i for i in r["issues"] if i["severity"] == "confirm" and i["code"] not in given]
        if r.get("duplicate"):
            r["status"] = "duplicate"
        elif blocks:
            r["status"] = "blocked"
        elif pending:
            r["status"] = "needs_confirmation"
        else:
            r["status"] = "ready"
        if r["status"] == "ready" and "missing_admission" in given and not r["admission_number"]:
            while _idkey(f"{PROVISIONAL_PREFIX}{n:04d}") in used:
                n += 1
            r["admission_number"] = f"{PROVISIONAL_PREFIX}{n:04d}"
            used.add(_idkey(r["admission_number"]))
            r["provisional_admission"] = True
        if r["status"] in ("ready", "duplicate"):
            # A decision already taken, and a row that will be skipped anyway, must
            # not keep asking for a decision in the review list.
            r["issues"] = [i for i in r["issues"] if i["severity"] != "confirm"]
        r["class_label"] = (r["level"]["name"] + (f" {r['stream']['name']}" if r["stream"] else "")) if r["level"] else ""
        r["level_id"] = r["level"]["id"] if r["level"] else None
        r["stream_id"] = r["stream"]["id"] if r["stream"] else None

    by_class = defaultdict(int)
    by_class_ready = defaultdict(int)
    by_stream = defaultdict(int)
    for r in rows:
        if r["class_label"]:
            by_class[r["class_label"]] += 1
            if r["status"] == "ready":
                by_class_ready[r["class_label"]] += 1
        if r["stream"]:
            by_stream[r["stream"]["name"]] += 1
        elif r["level"]:
            by_stream["No stream"] += 1
    total = len(rows)
    ready = sum(r["status"] == "ready" for r in rows)
    out["rows"] = rows
    out["summary"] = {
        "total": total,
        "ready": ready,
        "needs_confirmation": sum(r["status"] == "needs_confirmation" for r in rows),
        "blocked": sum(r["status"] == "blocked" for r in rows),
        "duplicates": sum(r["status"] == "duplicate" for r in rows),
        "skipped": total - ready,
        "needs_attention": sum(r["status"] in ("blocked", "needs_confirmation") for r in rows),
        "temporary_admission": sum(r["provisional_admission"] for r in rows),
        "by_class": dict(by_class),
        "by_class_ready": dict(by_class_ready),
        "by_stream": dict(by_stream),
    }
    return out
