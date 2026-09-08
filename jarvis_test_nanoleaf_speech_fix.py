import jarvis_nanoleaf_v1 as n

tests = [
    "Jarvis turn nanoleve on",
    "Jarvis make nano leave purple",
    "Jarvis set nanolife to 40 percent",
    "Jarvis turn nano leaf off",
    "Jarvis make nano leap blue",
]

print("=== Nanoleaf Speech Fix Test ===")

for raw in tests:
    fixed = n.norm(raw)
    ok = "nanoleaf" in fixed
    print(f"{raw} -> {fixed} : {'PASS' if ok else 'FAIL'}")
    assert ok

print()
print("PASS")
