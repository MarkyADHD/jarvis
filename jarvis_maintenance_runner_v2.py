"""Fixed, bounded, offline smoke/regression runner. No application imports."""
import ast
import json
from pathlib import Path
import sys
import time

# -I deliberately excludes the current directory; add only this trusted directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_guardian_v1 as guardian


CASES = {
    "maintenance_web_intent_text": [
        ("latest GTA 6 news", True), ("search the internet for cats", True),
        ("what happened today", True), ("check online", True),
        ("hello", False), ("play music", False), ("", False),
        (None, False), (42, False), (["latest"], False), ("x" * 8001, False),
    ],
    "maintenance_clean_web_reply": [
        (" Hello, Sir. ", "Hello, Sir."), ("I'm not sure on that one yet, Sir.", ""),
        ("im not sure on that one yet.", ""), ("", ""), (None, ""),
        (42, ""), (["answer"], ""), ("x" * 16001, ""),
    ],
}


def check_source(source, fixture_path=None):
    tree = ast.parse(source)
    compile(tree, "jarvis_app_v2.py", "exec")
    functions = guardian.isolated_functions(source, CASES)
    checks = 0
    started = time.perf_counter()
    for name, cases in CASES.items():
        for value, expected in cases:
            actual = functions[name](value)
            assert type(actual) is type(expected) and actual == expected, (name, repr(value)[:80], actual, expected)
            checks += 1
    # Owner-provided declarative regression cases. They cannot execute code.
    if fixture_path and Path(fixture_path).exists():
        fixtures = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        assert isinstance(fixtures, list) and len(fixtures) <= 1000
        for case in fixtures:
            assert set(case) == {"function", "input", "expected"}
            assert case["function"] in functions
            assert len(json.dumps(case)) < 50000
            actual = functions[case["function"]](case["input"])
            assert type(actual) is type(case["expected"]) and actual == case["expected"], case
            checks += 1
    # Port of the supplied installation's existing web-answer structural smoke.
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "web_fast_v2" in names:
        assert "grounded_web_answer_v3" in names
        web = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "web_fast_v2")
        web_source = ast.get_source_segment(source, web)
        assert "web_plan = grounded_web_answer_v3(c, web_context)" in web_source
        assert "brain.polish_web_plan" not in web_source
        checks += 3
    for _ in range(80):
        functions["maintenance_web_intent_text"]("find online the latest information")
        functions["maintenance_clean_web_reply"]("A clear answer from the research.")
    return {"ok": True, "checks": checks, "seconds": time.perf_counter() - started}


def main():
    source_path = Path(sys.argv[1])
    fixture_path = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(check_source(source_path.read_text(encoding="utf-8-sig"), fixture_path)))


if __name__ == "__main__":
    main()
