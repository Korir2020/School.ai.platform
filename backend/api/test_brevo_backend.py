import io
import json
import os
import urllib.error
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from api.mail_backend import BrevoEmailBackend

URLOPEN = "api.mail_backend.urllib.request.urlopen"


def _ok(status=201):
    resp = mock.MagicMock()
    resp.status = status
    cm = mock.MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


def _msg(backend=None):
    return EmailMessage(
        "Your code",
        "123456",
        "Marian <noreply@example.com>",
        ["head@example.com"],
        connection=backend or BrevoEmailBackend(),
    )


@override_settings(EMAIL_TIMEOUT=7)
class BrevoBackendTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DJANGO_BREVO_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sends_expected_request(self):
        with mock.patch(URLOPEN, return_value=_ok()) as m:
            sent = _msg().send()
        self.assertEqual(sent, 1)
        req = m.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(req.get_header("Api-key"), "test-key")
        body = json.loads(req.data)
        self.assertEqual(body["sender"], {"email": "noreply@example.com", "name": "Marian"})
        self.assertEqual(body["to"], [{"email": "head@example.com"}])
        self.assertEqual(body["subject"], "Your code")
        self.assertEqual(body["textContent"], "123456")
        self.assertEqual(m.call_args.kwargs["timeout"], 7)

    def test_http_error_raises_runtime_error(self):
        err = urllib.error.HTTPError(
            "https://api.brevo.com/v3/smtp/email", 400, "Bad", {},
            io.BytesIO(b'{"message":"sender invalid"}'),
        )
        with mock.patch(URLOPEN, side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                _msg().send()
        self.assertIn("400", str(ctx.exception))

    def test_network_error_propagates(self):
        with mock.patch(URLOPEN, side_effect=OSError("Network is unreachable")):
            with self.assertRaises(OSError):
                _msg().send()

    def test_missing_key_raises_and_sends_nothing(self):
        with mock.patch.dict(os.environ, {"DJANGO_BREVO_API_KEY": ""}):
            with mock.patch(URLOPEN) as m:
                with self.assertRaises(ImproperlyConfigured):
                    _msg(BrevoEmailBackend()).send()
        m.assert_not_called()

    def test_fail_silently_returns_zero(self):
        backend = BrevoEmailBackend(fail_silently=True)
        with mock.patch(URLOPEN, side_effect=OSError("down")):
            self.assertEqual(backend.send_messages([_msg(backend)]), 0)
