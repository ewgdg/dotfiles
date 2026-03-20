from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dotdrop_template_update.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dotdrop_template_update", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class DotdropTemplateUpdateTests(unittest.TestCase):
    def merge(self, template: str, live: str, *, emit_conflict_markers: bool = True) -> str:
        merged_lines, _stats = MODULE.merge_template(
            template.splitlines(keepends=True),
            live.splitlines(keepends=True),
            emit_conflict_markers=emit_conflict_markers,
        )
        return "".join(merged_lines)

    def test_updates_small_control_bounded_block_with_partial_match(self) -> None:
        template = """before
{%@@ if os == "linux" @@%}
a
b
{%@@ endif @@%}
after
"""
        live = """before
a
B
after
"""
        expected = """before
{%@@ if os == "linux" @@%}
a
B
{%@@ endif @@%}
after
"""
        self.assertEqual(self.merge(template, live), expected)

    def test_updates_single_line_control_bounded_block_with_zero_matches(self) -> None:
        template = """start
{%@@ if os == "linux" @@%}
foo
{%@@ endif @@%}
end
"""
        live = """start
bar
end
"""
        expected = """start
{%@@ if os == "linux" @@%}
bar
{%@@ endif @@%}
end
"""
        self.assertEqual(self.merge(template, live), expected)

    def test_emits_conflict_markers_by_default_for_ambiguous_branch(self) -> None:
        template = """start
{%@@ if os == "darwin" @@%}
darwin-value
{%@@ elif os == "linux" @@%}
linux-value
{%@@ else @@%}
fallback-value
{%@@ endif @@%}
end
"""
        live = """start
linux-new
end
"""
        expected = """start
{%@@ if os == "darwin" @@%}
darwin-value
{%@@ elif os == "linux" @@%}
<<<<<<< TEMPLATE
linux-value
=======
linux-new
>>>>>>> LIVE
{%@@ else @@%}
fallback-value
{%@@ endif @@%}
end
"""
        self.assertEqual(self.merge(template, live), expected)

    def test_can_explicitly_keep_ambiguous_branch_unchanged(self) -> None:
        template = """start
{%@@ if os == "darwin" @@%}
darwin-value
{%@@ elif os == "linux" @@%}
linux-value
{%@@ else @@%}
fallback-value
{%@@ endif @@%}
end
"""
        live = """start
linux-new
end
"""
        self.assertEqual(
            self.merge(template, live, emit_conflict_markers=False),
            template,
        )

    def test_updates_plain_literal_block_with_surrounding_anchors(self) -> None:
        template = """before
literal-one
literal-two
after
"""
        live = """before
literal-one
literal-two-updated
after
"""
        expected = """before
literal-one
literal-two-updated
after
"""
        self.assertEqual(self.merge(template, live), expected)


if __name__ == "__main__":
    unittest.main()
