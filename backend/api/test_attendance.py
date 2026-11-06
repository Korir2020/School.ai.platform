from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, AttendanceRecord, School, SchoolAdminProfile, Student, Term,
)


class AttendanceInterventionTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Attendance School", code="ATT")
        self.other = School.objects.create(name="Other", code="OTH")
        self.admin = User.objects.create_user("attendanceadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Attend", last_name="Student", admission_number="AT1")
        self.outsider = Student.objects.create(school=self.other, first_name="Other", last_name="Student", admission_number="OT1")

    def test_bulk_attendance_is_saved_and_school_scoped(self):
        self.client.force_authenticate(self.admin)
        day = "2026-10-13"
        saved = self.client.post("/api/attendance/", {"date": day, "records": [{"student_id": self.student.id, "status": "late"}, {"student_id": self.outsider.id, "status": "absent"}]}, format="json")
        self.assertEqual(saved.status_code, 403)
        self.assertEqual(AttendanceRecord.objects.count(), 0)
        saved = self.client.post("/api/attendance/", {"date": day, "records": [{"student_id": self.student.id, "status": "late"}]}, format="json")
        self.assertEqual(saved.status_code, 200)
        rows = self.client.get(f"/api/attendance/?date={day}")
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(rows.json()["students"][0]["status"], "late")
        self.assertEqual(len(rows.json()["students"]), 1)
        self.assertEqual(rows.json()["count"], 1)
        self.assertEqual(rows.json()["results"][0]["status"], "late")

    def test_attendance_roster_is_page_bounded(self):
        for i in range(55):
            Student.objects.create(school=self.school, first_name=f"Learner{i}",
                                   last_name="Page", admission_number=f"PG{i}")
        self.client.force_authenticate(self.admin)
        first = self.client.get("/api/attendance/?page_size=50")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["count"], 56)
        self.assertEqual(len(first.json()["results"]), 50)
        self.assertIsNotNone(first.json()["next"])
        second = self.client.get("/api/attendance/?page=2&page_size=50")
        self.assertEqual(len(second.json()["results"]), 6)

    def test_attendance_batch_upserts_without_duplicates_and_rejects_bad_rows(self):
        self.client.force_authenticate(self.admin)
        payload = {"date": "2026-10-13", "records": [{
            "student_id": self.student.id, "status": "late", "notes": "Bus delay",
        }]}
        self.assertEqual(self.client.post("/api/attendance/", payload, format="json").status_code, 200)
        payload["records"][0]["status"] = "present"
        self.assertEqual(self.client.post("/api/attendance/", payload, format="json").status_code, 200)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        record = AttendanceRecord.objects.get(student=self.student)
        self.assertEqual((record.status, record.notes), ("present", "Bus delay"))
        malformed = self.client.post("/api/attendance/", {
            "date": "2026-10-13", "records": [{
                "student_id": 1.5, "status": "absent",
            }],
        }, format="json")
        self.assertEqual(malformed.status_code, 400)

    def test_intervention_can_be_created_and_closed(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(f"/api/students/{self.student.id}/interventions/", {"reason": "absence", "notes": "Three absences this month", "action_plan": "Parent meeting", "follow_up_date": "2026-10-20"}, format="json")
        self.assertEqual(created.status_code, 201)
        intervention_id = created.json()["id"]
        closed = self.client.patch(f"/api/students/{self.student.id}/interventions/", {"id": intervention_id, "outcome": "improved"}, format="json")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["outcome"], "improved")
