from pathlib import Path

p = Path(r"C:\AI-Agent\jarvis_goal_mode_v32.py")
text = p.read_text(encoding="utf-8", errors="replace")

old_success = '''    return {
        "mode": "action",
        "reply": f"Done, {spoken_name}.",
        "steps": results
    }
'''

new_success = '''    return {
        "mode": "chat",
        "reply": f"Done, {spoken_name}.",
        "steps": []
    }
'''

old_failure = '''            return {
                "mode": "chat",
                "reply": f"I completed {index - 1} step(s), but stopped at step {index}: {message} {spoken_name}.",
                "steps": results
            }
'''

new_failure = '''            return {
                "mode": "chat",
                "reply": f"I completed {index - 1} step(s), but stopped at step {index}: {message} {spoken_name}.",
                "steps": []
            }
'''

changed = False

if old_success in text:
    text = text.replace(old_success, new_success, 1)
    changed = True

if old_failure in text:
    text = text.replace(old_failure, new_failure, 1)
    changed = True

p.write_text(text, encoding="utf-8")

print("Goal Mode double-execution fix applied." if changed else "Nothing changed - send me the file if the error continues.")
