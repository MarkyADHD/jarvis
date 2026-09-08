
from pathlib import Path
import ast

p = Path(r"C:\AI-Agent\jarvis_app_v2.py")
text = p.read_text(encoding="utf-8", errors="replace")

tree = ast.parse(text)
names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

print("=== Jarvis Latest-News Web Routing SAFE Test ===")
print()

assert "force_web_intent" in names
print("force_web_intent function: PASS")

module = ast.Module(
    body=[
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "force_web_intent"
    ],
    type_ignores=[],
)

code = compile(module, "<force_web_intent_test>", "exec")

def fake_normalise(text):
    return " ".join(str(text or "").lower().strip().split())

scope = {"app_normalise": fake_normalise}
exec(code, scope)

f = scope["force_web_intent"]

tests = [
    ("latest news on gta 6", True),
    ("give me the latest gta 6 news", True),
    ("what are the recent updates on gta 6", True),
    ("search online for gta 6", True),
    ("look up gta 6", True),
    ("tell me about gta 6", False),
]

for text, expected in tests:
    result = f(text)
    print(f"{text!r}: {result}")
    assert result == expected

print()
print("PASS")
print("This test does NOT launch Jarvis or perform a web search.")
