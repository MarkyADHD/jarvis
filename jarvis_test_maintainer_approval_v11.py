import jarvis_maintainer_v1 as m

print("=== Jarvis Maintainer Approval V1.1 SAFE Test ===")
print()

for name in (
    "pending_approval",
    "approval_status",
    "approve_pending_repair",
    "reject_pending_repair",
):
    ok = hasattr(m, name)
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    assert ok

print()
print("Current approval status:")
print(m.approval_status())

print()
print("PASS")
print("This test does NOT approve or deploy a repair.")
