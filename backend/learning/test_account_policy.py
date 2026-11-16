from datetime import date

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from .account_policy import age_band_for, age_on, independent_registration_policy, minimum_independent_age


class AccountAgePolicyTests(SimpleTestCase):
    today = date(2026, 11, 15)

    def test_exact_independent_minimum_and_just_below(self):
        self.assertEqual(age_band_for(date(2016, 11, 15), self.today), ("10_17", 10))
        self.assertEqual(age_band_for(date(2016, 11, 16), self.today), ("under_10", 9))
        self.assertEqual(independent_registration_policy(date(2016, 11, 15), self.today)["allowed_by_age"], True)
        self.assertEqual(independent_registration_policy(date(2016, 11, 16), self.today)["allowed_by_age"], False)

    def test_age_seventeen_and_eighteen_boundaries(self):
        self.assertEqual(age_band_for(date(2008, 11, 16), self.today), ("10_17", 17))
        self.assertEqual(age_band_for(date(2008, 11, 15), self.today), ("adult", 18))
        self.assertTrue(independent_registration_policy(date(2008, 11, 16), self.today)["guardian_required"])
        self.assertFalse(independent_registration_policy(date(2008, 11, 15), self.today)["guardian_required"])

    def test_unknown_future_and_implausible_birth_dates_fail_closed(self):
        for dob in (None, date(2027, 1, 1), date(1890, 1, 1)):
            with self.subTest(dob=dob):
                self.assertEqual(age_on(dob, self.today), None)
                self.assertEqual(independent_registration_policy(dob, self.today)["age_band"], "unknown")
                self.assertFalse(independent_registration_policy(dob, self.today)["allowed_by_age"])

    @override_settings(LEARNING_MIN_INDEPENDENT_AGE=12)
    def test_configured_threshold_may_increase_but_not_lower_approved_minimum(self):
        self.assertEqual(minimum_independent_age(), 12)
        self.assertFalse(independent_registration_policy(date(2015, 11, 15), self.today)["allowed_by_age"])
        self.assertTrue(independent_registration_policy(date(2014, 11, 15), self.today)["allowed_by_age"])

    @override_settings(LEARNING_MIN_INDEPENDENT_AGE=9)
    def test_config_below_approved_minimum_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            minimum_independent_age()
