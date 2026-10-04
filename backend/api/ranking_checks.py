from collections import defaultdict

from schools.models import Subject, TeacherAssignment


def missing_subjects(school_id, stream_of, grouped, all_subjects):
    """Students with SOME marks but not every expected subject.
    Expected = subjects assigned to the student's stream; if the stream has
    no assignments, fall back to every subject marked in this exam."""
    streams = {s for s in stream_of.values() if s is not None}
    assigned = defaultdict(set)
    rows = TeacherAssignment.objects.filter(
        school_id=school_id, stream_id__in=streams)
    for stream_id, subject_id in rows.values_list("stream_id", "subject_id"):
        assigned[stream_id].add(subject_id)
    ids = set(all_subjects).union(*assigned.values())
    names = dict(Subject.objects.filter(id__in=ids).values_list("id", "name"))
    out = {}
    for sid, got in grouped.items():
        expected = assigned.get(stream_of.get(sid)) or all_subjects
        gone = sorted(names[s] for s in expected if s not in got)
        if gone:
            out[sid] = gone
    return out
