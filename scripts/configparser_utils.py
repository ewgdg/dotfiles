from __future__ import annotations

import configparser


class CaseSensitiveRawConfigParser(configparser.RawConfigParser):
    """Preserve INI key casing for GTK and gsettings-managed files."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr
