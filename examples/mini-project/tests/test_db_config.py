#: Executable evidence for the c4spec constraint `db-connection-tls`.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db_config import (  # noqa: E402
    ALLOWED_SSLMODES,
    REQUIRED_SSLMODE,
    InsecureConfiguration,
    assert_tls,
    build_dsn,
)


class DbConnectionTlsTests(unittest.TestCase):
    def test_default_dsn_pins_tls(self):
        dsn = build_dsn(host="shop.db", database="products", user="api")
        self.assertIn("sslmode=require", dsn)
        self.assertEqual(assert_tls(dsn), REQUIRED_SSLMODE)

    def test_plaintext_fallback_modes_are_refused(self):
        for mode in ("disable", "allow", "prefer"):
            with self.subTest(mode=mode):
                with self.assertRaises(InsecureConfiguration):
                    build_dsn(host="shop.db", database="products", user="api", sslmode=mode)

    def test_dsn_without_sslmode_is_refused(self):
        with self.assertRaises(InsecureConfiguration):
            assert_tls("postgresql://api@shop.db/products")

    def test_duplicate_sslmode_cannot_hide_plaintext_fallback(self):
        for dsn in (
            "postgresql://api@shop.db/products?sslmode=require&sslmode=disable",
            "postgresql://api@shop.db/products?sslmode=disable&sslmode=require",
            "postgresql://api@shop.db/products?sslmode=require&sslmode=require",
        ):
            with self.subTest(dsn=dsn):
                with self.assertRaises(InsecureConfiguration):
                    assert_tls(dsn)

    def test_non_postgresql_scheme_is_refused(self):
        with self.assertRaises(InsecureConfiguration):
            assert_tls("https://shop.db/products?sslmode=require")

    def test_plaintext_dsn_is_refused(self):
        with self.assertRaises(InsecureConfiguration):
            assert_tls("postgresql://api@shop.db/products?sslmode=disable")

    def test_stronger_modes_are_accepted(self):
        for mode in ("verify-ca", "verify-full"):
            with self.subTest(mode=mode):
                dsn = build_dsn(host="shop.db", database="products", user="api", sslmode=mode)
                self.assertEqual(assert_tls(dsn), mode)
        self.assertEqual(ALLOWED_SSLMODES, ("require", "verify-ca", "verify-full"))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            build_dsn(host="shop.db", database="products", user="api", sslmode="bogus")


if __name__ == "__main__":
    unittest.main()
