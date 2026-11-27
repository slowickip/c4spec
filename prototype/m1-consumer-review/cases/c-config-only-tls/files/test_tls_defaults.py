import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db_config import (  # noqa: E402
    ENVIRONMENT_SSLMODES,
    InsecureConfiguration,
    assert_environment_tls,
    assert_tls,
    build_dsn_for_environment,
)


class EnvironmentTlsTests(unittest.TestCase):
    def test_production_dsn_pins_verify_full(self):
        dsn = build_dsn_for_environment("production", host="shop.db", database="products", user="api")
        self.assertIn("sslmode=verify-full", dsn)
        self.assertEqual(assert_tls(dsn), "verify-full")
        self.assertEqual(assert_environment_tls("production", dsn), "verify-full")

    def test_staging_dsn_stays_at_require(self):
        dsn = build_dsn_for_environment("staging", host="shop.db", database="products", user="api")
        self.assertIn("sslmode=require", dsn)
        self.assertEqual(assert_environment_tls("staging", dsn), "require")

    def test_production_refuses_a_weaker_dsn(self):
        dsn = build_dsn_for_environment("staging", host="shop.db", database="products", user="api")
        with self.assertRaises(InsecureConfiguration):
            assert_environment_tls("production", dsn)

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(ValueError):
            build_dsn_for_environment("qa", host="shop.db", database="products", user="api")

    def test_table_documents_both_environments(self):
        self.assertEqual(set(ENVIRONMENT_SSLMODES), {"production", "staging"})


if __name__ == "__main__":
    unittest.main()
