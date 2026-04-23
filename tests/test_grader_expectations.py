from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.grader_expectations import (
    GapReport,
    compute_gaps,
    extract_grader_expectations,
    extract_prompt_surface,
    format_asserted_literals_for_llm,
)


class TestExtractGraderExpectations(unittest.TestCase):
    def test_extracts_imports(self) -> None:
        test_code = (
            "from my_module import MyClass, helper_fn, CONSTANT\n"
            "import json\n"
        )
        exp = extract_grader_expectations([("test_demo.py", test_code)])
        self.assertIn("MyClass", exp.imported_names)
        self.assertIn("helper_fn", exp.imported_names)
        self.assertIn("CONSTANT", exp.imported_names)
        self.assertIn("my_module", exp.imported_modules)

    def test_extracts_method_calls(self) -> None:
        test_code = (
            "def test_thing():\n"
            "    obj = Foo()\n"
            "    result = obj.run_query('hello')\n"
            "    obj.store.compact('T1')\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertTrue(any("run_query" in m for m in exp.called_methods))
        self.assertTrue(any("compact" in m for m in exp.called_methods))

    def test_extracts_attribute_accesses(self) -> None:
        test_code = (
            "def test_attrs():\n"
            "    sys = create_system()\n"
            "    sys.llm_fn = lambda x: x\n"
            "    val = sys.store\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertTrue(any("llm_fn" in a for a in exp.accessed_attributes))
        self.assertTrue(any("store" in a for a in exp.accessed_attributes))

    def test_extracts_instantiated_classes(self) -> None:
        test_code = (
            "def test_create():\n"
            "    am = AccessManager()\n"
            "    sys = MultiTenantRAGSystem('/tmp', am, lambda x: x)\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertIn("AccessManager", exp.instantiated_classes)
        self.assertIn("MultiTenantRAGSystem", exp.instantiated_classes)

    def test_extracts_string_literals(self) -> None:
        test_code = (
            "def test_paths():\n"
            "    path = '/tmp/rag_enterprise_test/T1_000000.sst'\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertTrue(any("T1_000000.sst" in s for s in exp.string_literals))

    def test_handles_syntax_error_gracefully(self) -> None:
        exp = extract_grader_expectations([("bad.py", "def broken(:\n")])
        self.assertEqual(exp.imported_names, [])

    def test_deduplicates(self) -> None:
        test_code = (
            "from mod import Foo\n"
            "from mod import Foo\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertEqual(exp.imported_names.count("Foo"), 1)


class TestExtractAssertionLiterals(unittest.TestCase):
    def test_captures_assert_literal_in_result(self) -> None:
        test_code = (
            "def test_telegram():\n"
            "    result = redact('bot123456789:abcdef')\n"
            "    assert '123456789:***' in result\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertIn("123456789:***", exp.assertion_in_literals)
        self.assertEqual(exp.assertion_not_in_literals, [])
        self.assertEqual(exp.assertion_eq_literals, [])

    def test_captures_assert_literal_not_in_result(self) -> None:
        test_code = (
            "def test_secret_redacted():\n"
            "    result = redact('abc123def456')\n"
            "    assert 'abc123def456' not in result\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertIn("abc123def456", exp.assertion_not_in_literals)
        self.assertEqual(exp.assertion_in_literals, [])

    def test_captures_assert_equality_literal(self) -> None:
        test_code = (
            "def test_noop():\n"
            "    assert redact('HOME=/home/user') == 'HOME=/home/user'\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertIn("HOME=/home/user", exp.assertion_eq_literals)

    def test_filters_short_literals(self) -> None:
        test_code = (
            "def test_short():\n"
            "    assert 'x' in result\n"
            "    assert 'ok' in result\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertEqual(exp.assertion_in_literals, [])

    def test_ignores_non_literal_in_check(self) -> None:
        test_code = (
            "def test_contains():\n"
            "    needle = 'foo'\n"
            "    assert needle in result\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertEqual(exp.assertion_in_literals, [])

    def test_dedupes_repeated_literals(self) -> None:
        test_code = (
            "def test_one():\n"
            "    assert 'abc123def' in result\n"
            "def test_two():\n"
            "    assert 'abc123def' in result\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertEqual(exp.assertion_in_literals.count("abc123def"), 1)

    def test_ts_toContain_captures_literal(self) -> None:
        test_code = (
            "it('redacts', () => {\n"
            "  expect(redact('bot123456789:abcdef')).toContain('123456789:***');\n"
            "});\n"
        )
        exp = extract_grader_expectations(
            [("redact.test.ts", test_code)], language="typescript"
        )
        self.assertIn("123456789:***", exp.assertion_in_literals)

    def test_ts_not_toContain_captures_literal(self) -> None:
        test_code = (
            "it('hides secret', () => {\n"
            "  expect(redact('abc123def456')).not.toContain('abc123def456');\n"
            "});\n"
        )
        exp = extract_grader_expectations(
            [("redact.test.ts", test_code)], language="typescript"
        )
        self.assertIn("abc123def456", exp.assertion_not_in_literals)


class TestFormatAssertedLiteralsForLLM(unittest.TestCase):
    def test_returns_empty_when_no_literals(self) -> None:
        test_code = "def test_smoke():\n    assert redact('x') is not None\n"
        exp = extract_grader_expectations([("test_x.py", test_code)])
        self.assertEqual(format_asserted_literals_for_llm(exp), "")

    def test_renders_all_three_buckets(self) -> None:
        test_code = (
            "def test_many():\n"
            "    assert '123456789:***' in result\n"
            "    assert 'abc123def456' not in result\n"
            "    assert redact('HOME=/home/user') == 'HOME=/home/user'\n"
        )
        exp = extract_grader_expectations([("test_x.py", test_code)])
        text = format_asserted_literals_for_llm(exp)
        self.assertIn("Must appear", text)
        self.assertIn("123456789:***", text)
        self.assertIn("Must NOT appear", text)
        self.assertIn("abc123def456", text)
        self.assertIn("Exact equality", text)
        self.assertIn("HOME=/home/user", text)
        self.assertIn("direct_contradiction", text)


class TestExtractPromptSurface(unittest.TestCase):
    def test_extracts_backtick_symbols(self) -> None:
        prompt = "Use `MyClass` and call `helper_fn` to process data."
        surface = extract_prompt_surface(prompt)
        self.assertIn("MyClass", surface.mentioned_symbols)
        self.assertIn("helper_fn", surface.mentioned_symbols)

    def test_extracts_def_and_class_from_code_blocks(self) -> None:
        prompt = "```python\ndef ingest(self, text: str) -> int:\nclass AccessManager:\n```"
        surface = extract_prompt_surface(prompt)
        self.assertIn("ingest", surface.code_block_defs)
        self.assertIn("AccessManager", surface.code_block_defs)

    def test_extracts_module_names(self) -> None:
        prompt = "Create `multi_tenant_rag_system.py` in the workspace."
        surface = extract_prompt_surface(prompt)
        self.assertIn("multi_tenant_rag_system", surface.mentioned_modules)

    def test_extracts_dotted_references(self) -> None:
        prompt = "The `sys.store` attribute must be public."
        surface = extract_prompt_surface(prompt)
        self.assertIn("store", surface.mentioned_symbols)


class TestComputeGaps(unittest.TestCase):
    def test_finds_hidden_imports(self) -> None:
        test_code = "from my_module import VectorStore, AccessManager\n"
        prompt = "Implement `AccessManager` class."

        exp = extract_grader_expectations([("test.py", test_code)])
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertIn("VectorStore", gaps.imports_not_in_prompt)
        self.assertNotIn("AccessManager", gaps.imports_not_in_prompt)

    def test_finds_hidden_method_calls(self) -> None:
        test_code = (
            "def test_x():\n"
            "    am = AccessManager()\n"
            "    am.add_user('u1', 'T1', 'admin')\n"
        )
        prompt = "class AccessManager: manages permissions"

        exp = extract_grader_expectations([("test.py", test_code)])
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertTrue(any("add_user" in m for m in gaps.methods_not_in_prompt))

    def test_finds_hidden_attribute_accesses(self) -> None:
        test_code = (
            "def test_x():\n"
            "    sys = create()\n"
            "    sys.llm_fn = lambda x: x\n"
        )
        prompt = "class MultiTenantRAGSystem: orchestrates"

        exp = extract_grader_expectations([("test.py", test_code)])
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertTrue(any("llm_fn" in a for a in gaps.attributes_not_in_prompt))

    def test_no_gaps_when_prompt_covers_everything(self) -> None:
        test_code = (
            "from my_module import Widget\n"
            "def test_x():\n"
            "    w = Widget()\n"
            "    w.render()\n"
        )
        prompt = "Implement `Widget` class with `render()` method in `my_module.py`."

        exp = extract_grader_expectations([("test.py", test_code)])
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertNotIn("Widget", gaps.imports_not_in_prompt)
        self.assertNotIn("render", gaps.methods_not_in_prompt)

    def test_filters_noise(self) -> None:
        test_code = (
            "import pytest\n"
            "import json\n"
            "from pathlib import Path\n"
            "def test_x():\n"
            "    assert isinstance(result, dict)\n"
        )
        prompt = "Build a library."

        exp = extract_grader_expectations([("test.py", test_code)])
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertNotIn("pytest", gaps.imports_not_in_prompt)
        self.assertNotIn("json", gaps.imports_not_in_prompt)
        self.assertNotIn("Path", gaps.imports_not_in_prompt)

    def test_format_for_llm_shows_gaps(self) -> None:
        report = GapReport(
            imports_not_in_prompt=["VectorStore"],
            methods_not_in_prompt=["add_user"],
            attributes_not_in_prompt=["sys.store", "sys.llm_fn"],
        )
        text = report.format_for_llm()
        self.assertIn("VectorStore", text)
        self.assertIn("add_user", text)
        self.assertIn("sys.store", text)
        self.assertIn("4 gaps", text)

    def test_format_for_llm_clean_report(self) -> None:
        report = GapReport()
        text = report.format_for_llm()
        self.assertIn("No deterministic gaps", text)


class TestRealTaskValidation(unittest.TestCase):
    """Test against actual generated task files in the repo."""

    def _load_task_files(self, task_name: str) -> tuple[str, list[tuple[str, str]]]:
        task_dir = Path(__file__).resolve().parents[1] / "tasks" / task_name
        prompt_path = task_dir / "prompt.md"
        if not prompt_path.exists():
            self.skipTest(f"Task {task_name} not found")
        prompt = prompt_path.read_text(encoding="utf-8")
        tests_dir = task_dir / "tests"
        test_files = []
        if tests_dir.is_dir():
            for f in sorted(tests_dir.glob("*.py")):
                test_files.append((f.name, f.read_text(encoding="utf-8")))
        return prompt, test_files

    def test_file_operations_task_has_minimal_gaps(self) -> None:
        prompt, test_files = self._load_task_files("file_operations")
        if not test_files:
            self.skipTest("No test files")

        exp = extract_grader_expectations(test_files)
        surface = extract_prompt_surface(prompt)
        gaps = compute_gaps(exp, surface)

        self.assertNotIn("ShellFileOperations", gaps.imports_not_in_prompt)
        self.assertNotIn("ReadResult", gaps.imports_not_in_prompt)
        self.assertNotIn("WriteResult", gaps.imports_not_in_prompt)

    def test_anthropic_adapter_task_extracts_real_imports(self) -> None:
        prompt, test_files = self._load_task_files("anthropic_adapter")
        if not test_files:
            self.skipTest("No test files")

        exp = extract_grader_expectations(test_files)
        self.assertTrue(len(exp.imported_names) > 5)
        self.assertTrue(any("build_anthropic_client" in n for n in exp.imported_names))


if __name__ == "__main__":
    unittest.main()
