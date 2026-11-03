"""Regression tests: one dancer's class selection must not replace another's."""
from types import SimpleNamespace
from django.test import SimpleTestCase
from .views import _registration_student_state, _store_registration_student_state


class MultiDancerAssignmentTests(SimpleTestCase):
    def test_independent_class_selection_roundtrip(self):
        session = SimpleNamespace(student_data={}, updated_at=None)
        students = [
            {"draft_key": "existing-11", "existing_student_id": 11, "student_first_name": "One"},
            {"draft_key": "existing-22", "existing_student_id": 22, "student_first_name": "Two"},
        ]
        _store_registration_student_state(session, students, {"existing-11": [101], "existing-22": [202]}, save=False)
        loaded, selected = _registration_student_state(session)
        self.assertEqual(len(loaded), 2)
        selected["existing-11"] = [101, 103]
        _store_registration_student_state(session, loaded, selected, save=False)
        _, after = _registration_student_state(session)
        self.assertEqual(after["existing-11"], [101, 103])
        self.assertEqual(after["existing-22"], [202])
