import unittest

from app.database import normalize_database_url


class DeploymentDatabaseConfigTests(unittest.TestCase):
    def test_neon_style_postgresql_url_uses_psycopg_v3(self):
        value = normalize_database_url(
            "postgresql://user:secret@example.neon.tech/app?sslmode=require"
        )
        self.assertTrue(value.startswith("postgresql+psycopg://"))
        self.assertIn("sslmode=require", value)

    def test_explicit_psycopg_url_is_unchanged(self):
        value = "postgresql+psycopg://user:secret@localhost/app"
        self.assertEqual(normalize_database_url(value), value)


if __name__ == "__main__":
    unittest.main()
