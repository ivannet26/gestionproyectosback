import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from apps.authentication.mail import DeliveryError, send_link


@override_settings(RESEND_API_KEY="synthetic-api-key", RESEND_FROM_EMAIL="accounts@example.com", FRONTEND_URL="http://localhost:5173")
class MailProviderTests(SimpleTestCase):
    @patch("apps.authentication.mail.urlopen")
    def test_success_requires_provider_message_identifier(self, urlopen):
        response = MagicMock(status=200)
        response.read.return_value = json.dumps({"id": "synthetic-message-id"}).encode()
        urlopen.return_value.__enter__.return_value = response
        self.assertEqual(send_link("worker@example.com", "Sintético", "activation", "synthetic-link-token"), "synthetic-message-id")
        request = urlopen.call_args.args[0]
        self.assertIn("/activar#token=", json.loads(request.data)["text"])
        self.assertTrue(request.has_header("Idempotency-key"))

    @patch("apps.authentication.mail.urlopen")
    def test_success_http_without_id_is_not_reported_as_sent(self, urlopen):
        response = MagicMock(status=200)
        response.read.return_value = b"{}"
        urlopen.return_value.__enter__.return_value = response
        with self.assertRaises(DeliveryError) as raised:
            send_link("worker@example.com", "Sintético", "activation", "synthetic-link-token")
        self.assertEqual(raised.exception.delivery_status, "unknown")

    @patch("apps.authentication.mail.urlopen", side_effect=TimeoutError)
    def test_timeout_is_an_unconfirmed_delivery(self, urlopen):
        with self.assertRaises(DeliveryError) as raised:
            send_link("worker@example.com", "Sintético", "activation", "synthetic-link-token")
        self.assertEqual(raised.exception.delivery_status, "unknown")

    @patch("apps.authentication.mail.urlopen")
    def test_provider_rejection_is_a_failed_delivery(self, urlopen):
        urlopen.side_effect = HTTPError("https://api.resend.com/emails", 422, "synthetic rejection", {}, None)
        with self.assertRaises(DeliveryError) as raised:
            send_link("worker@example.com", "Sintético", "activation", "synthetic-link-token")
        self.assertEqual(raised.exception.delivery_status, "failed")

    @override_settings(RESEND_API_KEY="")
    @patch("apps.authentication.mail.urlopen")
    def test_missing_configuration_does_not_contact_provider(self, urlopen):
        with self.assertRaises(DeliveryError):
            send_link("worker@example.com", "Sintético", "activation", "synthetic-link-token")
        urlopen.assert_not_called()
