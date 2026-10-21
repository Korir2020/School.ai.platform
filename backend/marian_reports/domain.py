from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class NotFound(LookupError): ...
class PermissionDenied(PermissionError): ...


class ReportNotReady(Exception):
    """Raised when a report would be misleading (unpublished / incomplete / wrong membership)."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class School:
    id: str
    name: str
    short_name: str
    address: str = ""
    phone: str = ""
    motto: str = ""
    principal_name: str = ""
    logo_path: Optional[str] = None      # file in private storage; monogram drawn if None


@dataclass(frozen=True)
class Student:
    id: str
    school_id: str
    adm_no: str
    full_name: str
    gender: str                           # "F" | "M" | ""
    class_name: str                       # e.g. "Form 3"
    stream: str                           # e.g. "East"
    kcpe_score: Optional[int] = None
    status: str = "active"                # active | withdrawn


@dataclass(frozen=True)
class Exam:
    id: str
    school_id: str
    name: str
    term: int
    year: int
    published: bool
    sequence: int                         # chronological order, for history
    closing_date: str = ""
    next_term_opens: str = ""


@dataclass(frozen=True)
class Attendance:
    """Days for one student over the reporting period. Unrecorded days stay unrecorded
    (present + absent may be less than days_open); nothing is inferred."""
    days_open: int
    days_present: int
    days_absent: int
    days_late: int = 0


@dataclass(frozen=True)
class User:
    """Authenticated principal. In the main app this is derived from the real session,
    never from request parameters."""
    id: str
    school_id: str
    role: str                             # admin | teacher | guardian | student
    class_names: tuple = ()               # teachers: classes they may view ("*" = all)
    student_ids: tuple = ()               # guardians/students: linked student ids
    can_view_fees: bool = False


class DataSource(ABC):
    """Integration interface. Every method is tenant-scoped by school_id.
    Map these to the real Django ORM models in School.ai.platform."""
    @abstractmethod
    def get_school(self, school_id: str) -> School: ...
    @abstractmethod
    def get_exam(self, school_id: str, exam_id: str) -> Exam: ...
    @abstractmethod
    def list_exams(self, school_id: str) -> list: ...
    @abstractmethod
    def get_student(self, school_id: str, student_id: str) -> Student: ...
    @abstractmethod
    def list_students(self, school_id: str, class_name: Optional[str] = None,
                      stream: Optional[str] = None) -> list: ...
    @abstractmethod
    def get_entries(self, school_id: str, exam_id: str, student_id: str) -> list: ...
    @abstractmethod
    def get_remarks(self, school_id: str, exam_id: str, student_id: str) -> dict: ...
    @abstractmethod
    def get_fee_note(self, school_id: str, student_id: str) -> Optional[str]: ...
    def get_attendance(self, school_id: str, exam_id: str, student_id: str) -> Optional["Attendance"]:
        """Optional. Return None when attendance is not recorded; the report then omits the section."""
        return None
