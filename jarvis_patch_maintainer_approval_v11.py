from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_maintainer_v1.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_maintainer_v1.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_maintainer_v1_backup_before_approval_v11_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

helper = r'''

def pending_approval():
    items = _read_lines(CHANGE_LOG)

    for item in reversed(items):
        if item.get("status") != "awaiting_approval":
            continue
        if item.get("approval_resolved"):
            continue

        target = Path(str(item.get("target", "") or ""))
        staged = Path(str(item.get("staged", "") or ""))

        if target.exists() and staged.exists():
            return item

    return None


def approval_status():
    item = pending_approval()

    if not item:
        return "There is no repair waiting for approval."

    target = Path(str(item.get("target", "") or "")).name
    diagnosis = str(item.get("diagnosis", "") or "").strip()

    if diagnosis:
        return f"A repair for {target} is waiting for approval. Diagnosis: {diagnosis}"

    return f"A repair for {target} is waiting for approval."


def _rewrite_change_log(updated_item):
    items = _read_lines(CHANGE_LOG)

    target_created = updated_item.get("created_at")
    target_path = updated_item.get("target")
    target_staged = updated_item.get("staged")

    changed = False

    for item in items:
        if (
            item.get("created_at") == target_created
            and item.get("target") == target_path
            and item.get("staged") == target_staged
            and item.get("status") == "awaiting_approval"
        ):
            item.update(updated_item)
            changed = True
            break

    if changed:
        with CHANGE_LOG.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")


def approve_pending_repair():
    item = pending_approval()

    if not item:
        return False, "There is no pending repair to approve."

    target = Path(str(item.get("target", "") or ""))
    staged = Path(str(item.get("staged", "") or ""))

    if not target.exists():
        return False, "The live target file no longer exists."

    if not staged.exists():
        return False, "The staged repair no longer exists."

    if target.parent.resolve() != PROJECT_ROOT.resolve():
        return False, "Guardian blocked approval outside C:\\AI-Agent."

    if target.name.lower() == "jarvis_guardian_v1.py":
        return False, "Guardian cannot approve modifications to itself."

    try:
        old_text = target.read_text(encoding="utf-8", errors="replace")
        new_text = staged.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"I couldn't read the repair files: {e}"

    gate = guardian.inspect_change(target, old_text, new_text)

    if not gate.get("allowed"):
        return False, (
            "Guardian still blocks this repair: "
            + "; ".join(gate.get("reasons", []))
        )

    valid, staged_or_error = _validate(target, new_text)

    if not valid:
        return False, f"The pending repair no longer validates: {staged_or_error}"

    diagnosis = str(item.get("diagnosis", "") or "").strip()

    ok, info = _deploy(
        target,
        Path(staged_or_error),
        gate,
        diagnosis,
    )

    if not ok:
        return False, info

    item["approval_resolved"] = True
    item["approval_result"] = "approved_and_applied"
    item["approved_at"] = now()
    _rewrite_change_log(item)

    return True, (
        f"Approved and deployed the pending repair to {target.name}. "
        "A rollback backup was created."
    )


def reject_pending_repair():
    item = pending_approval()

    if not item:
        return False, "There is no pending repair to reject."

    staged = Path(str(item.get("staged", "") or ""))
    target_name = Path(str(item.get("target", "") or "")).name

    item["approval_resolved"] = True
    item["approval_result"] = "rejected"
    item["rejected_at"] = now()
    _rewrite_change_log(item)

    try:
        if staged.exists():
            staged.unlink()
    except Exception:
        pass

    return True, f"Rejected the pending repair for {target_name}."

'''

if "def approve_pending_repair(" not in text:
    marker = "\ndef recent_changes(limit=8):\n"
    if marker not in text:
        raise SystemExit("Could not find recent_changes() insertion point.")
    text = text.replace(marker, helper + marker, 1)

command_anchor = '''    if c in {
        "what have you changed",
        "recent maintenance",
        "maintenance history",
    }:
'''

approval_commands = '''    if c in {
        "approval status",
        "pending repair",
        "pending approval",
        "what is waiting for approval",
    }:
        return {
            "mode": "chat",
            "reply": f"{approval_status()} {spoken_name}.",
            "steps": [],
        }

    if c in {
        "approve pending repair",
        "approve the pending repair",
        "approve repair",
        "approve the repair",
        "apply pending repair",
        "apply the pending repair",
    }:
        _, message = approve_pending_repair()
        return {
            "mode": "chat",
            "reply": f"{message} {spoken_name}.",
            "steps": [],
        }

    if c in {
        "reject pending repair",
        "reject the pending repair",
        "reject repair",
        "cancel pending repair",
        "cancel the pending repair",
    }:
        _, message = reject_pending_repair()
        return {
            "mode": "chat",
            "reply": f"{message} {spoken_name}.",
            "steps": [],
        }

'''

if '"approve pending repair"' not in text:
    if command_anchor not in text:
        raise SystemExit("Could not find maintainer command insertion point.")
    text = text.replace(command_anchor, approval_commands + command_anchor, 1)

P.write_text(text, encoding="utf-8")

verify = P.read_text(encoding="utf-8", errors="replace")

for required in (
    "def pending_approval(",
    "def approve_pending_repair(",
    "def reject_pending_repair(",
    '"approve pending repair"',
):
    if required not in verify:
        raise SystemExit("Patch verification failed: " + required)

print("Jarvis Maintainer Approval V1.1 installed.")
print("Backup:", backup)
print("Verification passed.")
