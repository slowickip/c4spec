import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.payments import PaymentDeclined, authorize  # noqa: E402


class AuthorizationTests(unittest.TestCase):
    def test_authorization_id_encodes_no_card_data(self):
        reference = authorize(1999, "EUR", "tok_visa")
        self.assertEqual(reference, "auth-eur-1999")

    def test_missing_token_is_declined(self):
        with self.assertRaises(PaymentDeclined):
            authorize(1999, "EUR", "")

    def test_non_positive_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            authorize(0, "EUR", "tok_visa")


if __name__ == "__main__":
    unittest.main()
