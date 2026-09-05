import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DatabaseConfigurationTests(unittest.TestCase):
    def test_database_url_is_required_and_no_credential_fallback_exists(self):
        source = (ROOT / "src" / "db" / "helpers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        string_values = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        literal_database_urls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "DATABASE_URL" for target in node.targets):
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                literal_database_urls.append(node.value.value)

        self.assertEqual([], literal_database_urls)
        self.assertIn("DATABASE_URL is required", string_values)


if __name__ == "__main__":
    unittest.main()
