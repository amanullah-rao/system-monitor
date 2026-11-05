# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Developer tool: list sentences wrapped in tr()/N_() and check the translations.

    python tools_i18n.py            report missing and unused Korean entries
    python tools_i18n.py --list     print every sentence that needs translating
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKERS = {"tr", "N_"}


def find_sentences() -> dict[str, list[str]]:
    """Every literal passed to tr() or N_(), with the files that use it."""
    found: dict[str, list[str]] = {}
    for path in sorted([*ROOT.glob("*.py"), *ROOT.glob("styles/*.py")]):
        if path.name in ("translations_ko.py", "tools_i18n.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in MARKERS
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.setdefault(node.args[0].value, []).append(path.name)
    # Shown through tr(app_info.DESCRIPTION), so it isn't a literal in the code.
    import app_info

    found.setdefault(app_info.DESCRIPTION, ["app_info.py"])
    return found


def main() -> int:
    sentences = find_sentences()
    if "--list" in sys.argv:
        for sentence in sentences:
            print(repr(sentence))
        return 0
    from translations_ko import KOREAN

    missing = [s for s in sentences if s not in KOREAN]
    unused = [s for s in KOREAN if s not in sentences]
    bad_placeholders = []
    import re

    pattern = re.compile(r"\{(\w+)\}")
    for sentence, korean in KOREAN.items():
        if set(pattern.findall(sentence)) != set(pattern.findall(korean)):
            bad_placeholders.append(sentence)
    print(f"{len(sentences)} sentences, {len(KOREAN)} Korean entries")
    for title, items in (
        ("Missing a Korean translation", missing),
        ("In translations_ko.py but not used", unused),
        ("Placeholders differ from the English", bad_placeholders),
    ):
        if items:
            print(f"\n{title}:")
            for item in items:
                print("  ", repr(item))
    return 1 if (missing or bad_placeholders) else 0


if __name__ == "__main__":
    raise SystemExit(main())
