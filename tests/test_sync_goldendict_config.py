from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/goldendict/scripts/sync_goldendict_config.py"
)
_MODULE_SPEC = importlib.util.spec_from_file_location(
    "goldendict_sync_module", _MODULE_PATH
)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise RuntimeError(f"failed to load goldendict sync module from {_MODULE_PATH}")
module = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(module)


TEMPLATE_PLACEHOLDER = "{{ vars.goldendict.dictionary_dir }}"
TEMPLATE_VALUE = "${XDG_DOCUMENTS_DIR:-$HOME/Documents}/Dictionaries"
SAMPLE_DICTIONARY_PATH = "/home/tester/Documents/Dictionaries"


def test_patch_xml_text_replaces_dictionary_path_with_template_var() -> None:
    input_text = """<?xml version=\"1.0\" ?>
<config>
  <paths>
    <path recursive=\"1\">/home/tester/Documents/Dictionaries</path>
  </paths>
  <sounddirs/>
</config>
"""

    result = module.patch_xml_text(input_text)

    assert TEMPLATE_PLACEHOLDER in result
    assert SAMPLE_DICTIONARY_PATH not in result


def test_patch_xml_text_rejects_multiple_distinct_dictionary_paths() -> None:
    input_text = """<?xml version=\"1.0\" ?>
<config>
  <paths>
    <path recursive=\"1\">/home/tester/Documents/Dictionaries</path>
    <path recursive=\"1\">/mnt/shared/Dictionaries</path>
  </paths>
</config>
"""

    with pytest.raises(ValueError, match="multiple distinct dictionary paths"):
        module.patch_xml_text(input_text)


def test_expand_shell_path_prefers_xdg_documents_dir(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", "/srv/docs")

    assert module.expand_shell_path(TEMPLATE_VALUE) == "/srv/docs/Dictionaries"


def test_expand_shell_path_falls_back_to_home_documents(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.delenv("XDG_DOCUMENTS_DIR", raising=False)

    assert module.expand_shell_path(TEMPLATE_VALUE) == "/home/tester/Documents/Dictionaries"


def test_expand_shell_path_supports_profile_overrides_with_other_env_vars(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("CUSTOM_DICT_DIR", "/srv/custom-dicts")

    assert (
        module.expand_shell_path("${CUSTOM_DICT_DIR:-$HOME/Documents}/foo")
        == "/srv/custom-dicts/foo"
    )


def test_render_repo_xml_replaces_template_placeholder_with_expanded_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", "/srv/docs")

    repo_path = tmp_path / "config.xml"
    monkeypatch.setattr(
        module,
        "render_repo_template",
        lambda repo_path: f"<config><paths><path>{TEMPLATE_VALUE}</path></paths></config>",
    )

    rendered_xml = module.render_repo_xml(repo_path)

    assert "/srv/docs/Dictionaries" in rendered_xml
    assert TEMPLATE_PLACEHOLDER not in rendered_xml
