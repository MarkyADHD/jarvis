
from pathlib import Path
import ast

P = Path(r"C:\AI-Agent\jarvis_app_v2.py")
text = P.read_text(encoding="utf-8", errors="replace")

tree = ast.parse(text)
funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

print("=== Jarvis Web Answer V3 SAFE Test ===")

assert "grounded_web_answer_v3" in funcs
print("grounded_web_answer_v3: PASS")

assert "web_fast_v2" in funcs
print("web_fast_v2: PASS")

section = text[text.find("def web_fast_v2"):text.find("def speak_v2")]

assert "web_plan = grounded_web_answer_v3(c, web_context)" in section
print("grounded route: PASS")

assert "brain.polish_web_plan" not in section
print("old overwrite path removed: PASS")

print("PASS")
