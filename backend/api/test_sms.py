import json
import os
from unittest import mock

from django.test import SimpleTestCase

from api import sms


class PhoneTests(SimpleTestCase):
    def test_kenyan_formats_normalise_to_e164(self):
        for raw in ("0712345678", "712345678", "254712345678", "+254 712-345-678", "00254712345678"):
            self.assertEqual(sms.normalize_phone(raw), "+254712345678", raw)
        self.assertEqual(sms.normalize_phone("0112345678"), "+254112345678")

    def test_bad_numbers_rejected(self):
        for raw in ("", "12345", "0812345678", "+25471234", "phone", "2540712345678"):
            self.assertEqual(sms.normalize_phone(raw), "", raw)

    def test_long_text_clipped_to_three_segments(self):
        self.assertEqual(len(sms.clip("x" * 1000)), 459)


class _Resp:
    def __init__(self, body):
        self.body, self.status = body, 201
    def read(self):
        return json.dumps(self.body).encode()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class ProviderTests(SimpleTestCase):
    @mock.patch.dict(os.environ, {"DJANGO_SMS_PROVIDER": ""}, clear=False)
    def test_no_provider_sends_nothing(self):
        out = sms.send_bulk(["+254712345678"], "hi")
        self.assertEqual(out["+254712345678"][0], "not_configured")

    @mock.patch.dict(os.environ, {"DJANGO_SMS_PROVIDER": "africastalking", "DJANGO_AT_USERNAME": "sandbox", "DJANGO_AT_API_KEY": "k"})
    def test_africastalking_per_number_result(self):
        body = {"SMSMessageData": {"Recipients": [
            {"number": "+254712345678", "statusCode": 101, "status": "Success", "cost": "KES 0.8000"},
            {"number": "+254700000000", "statusCode": 403, "status": "InvalidPhoneNumber"}]}}
        with mock.patch("urllib.request.urlopen", return_value=_Resp(body)) as op:
            out = sms.send_bulk(["+254712345678", "+254700000000"], "Hello")
        req = op.call_args[0][0]
        self.assertIn("sandbox", req.full_url)
        self.assertEqual(req.get_header("Apikey"), "k")
        self.assertEqual(out["+254712345678"][0], "sent")
        self.assertEqual(out["+254700000000"], ("failed", "InvalidPhoneNumber"))

    @mock.patch.dict(os.environ, {"DJANGO_SMS_PROVIDER": "africastalking", "DJANGO_AT_USERNAME": "marian", "DJANGO_AT_API_KEY": "k"})
    def test_network_failure_marks_all_failed(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            out = sms.send_bulk(["+254712345678"], "Hello")
        self.assertEqual(out["+254712345678"][0], "failed")

    @mock.patch.dict(os.environ, {"DJANGO_SMS_PROVIDER": "africastalking", "DJANGO_AT_USERNAME": "marian"})
    def test_missing_key_means_not_configured(self):
        os.environ.pop("DJANGO_AT_API_KEY", None)
        self.assertFalse(sms.is_configured())
