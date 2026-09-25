"""Guardian V2: DISABLED at the user's explicit request (2026-09-08).

This module used to be a deny-by-default AST policy restricting Jarvis's
self-maintenance feature (jarvis_maintainer_v1.py) to auto-editing two
named helper functions in jarvis_app_v2.py, with heavy sandboxing against
anything touching subprocess/exec/eval/imports/credentials/etc. The user
asked for it removed after being told exactly what it restricted (it has
no bearing on voice commands, file access, or anything else in Jarvis --
only on the automated code-patching pipeline). Kept as a real module
(not deleted) so jarvis_maintainer_v1.py's imports and call sites keep
working unchanged; every check now simply allows.
"""
import ast
import difflib
from pathlib import Path

VERSION = "2.0.0-disabled"
PROTECTED_FILES = frozenset()
EDITABLE_FUNCTIONS = {}


def inspect_change(path, old_text, new_text):
    """Always allows. Still computes real diff stats for the maintainer's
    own logging/receipts, since those aren't a safety mechanism."""
    changed_lines = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, old_text.splitlines(), new_text.splitlines()
        ).get_opcodes()
        if tag != "equal"
    )

    functions = []
    try:
        old = ast.parse(old_text)
        new = ast.parse(new_text)
        old_funcs = {n.name for n in old.body if isinstance(n, ast.FunctionDef)}
        new_funcs = {n.name for n in new.body if isinstance(n, ast.FunctionDef)}
        functions = sorted(old_funcs | new_funcs)
    except Exception:
        pass

    return {
        "allowed": True,
        "auto_apply": True,
        "reasons": [],
        "warnings": [],
        "changed_lines": changed_lines,
        "functions": functions,
        "policy_version": VERSION,
    }


def isolated_functions(source, names):
    """No sandboxing: extracts and executes the requested functions with
    real builtins, in a fresh namespace."""
    tree = ast.parse(source)
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]

    if len(selected) != len(set(names)):
        raise ValueError("Expected exactly one definition of each named function")

    namespace = {}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(Path("<guardian-disabled>")), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}
