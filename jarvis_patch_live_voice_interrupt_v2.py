
from pathlib import Path
from datetime import datetime
import shutil

APP = Path(r"C:\AI-Agent\jarvis_app.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.stem}_backup_before_live_interrupt_v2_{stamp}{path.suffix}")
    shutil.copy2(path, dst)
    return dst


def main():
    if not APP.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_app.py")

    text = APP.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP)

    if "def is_live_voice_interrupt_text(" not in text:
        anchor = "\ndef is_stop_talking_command(command):\n"

        helper = r"""

def is_live_voice_interrupt_text(text):
    # High-priority speech interrupt used only while Jarvis is talking.
    # Require wake-name + stop/cancel wording to reduce self-triggering.
    cleaned = normalize_transcript(text)
    if not cleaned:
        return False

    stop_words = [
        "stop",
        "cancel",
        "quiet",
        "be quiet",
        "shut up",
        "stop talking",
        "silence",
        "abort",
    ]

    wake_names = list(WAKE_WORD_ALIASES)

    for wake in wake_names:
        if not re.search(rf"\b{re.escape(wake)}\b", cleaned):
            continue

        for stop_word in stop_words:
            if re.search(rf"\b{re.escape(stop_word)}\b", cleaned):
                return True

    return False

"""

        if anchor not in text:
            raise RuntimeError("Could not find is_stop_talking_command() anchor.")

        text = text.replace(anchor, helper + anchor, 1)

    state_anchor = """    started_while_jarvis_was_speaking = False

    try:
"""

    if "live_interrupt_chunks = []" not in text:
        state_block = """    started_while_jarvis_was_speaking = False

    # Dedicated rolling buffer for "Jarvis stop" while TTS is playing.
    live_interrupt_chunks = []
    live_interrupt_bytes = 0
    last_live_interrupt_check = 0.0
    LIVE_INTERRUPT_WINDOW_SECONDS = 2.4
    LIVE_INTERRUPT_MIN_SECONDS = 0.9
    LIVE_INTERRUPT_CHECK_INTERVAL = 0.65

    try:
"""

        if state_anchor not in text:
            raise RuntimeError("Could not find voice_listener_loop state anchor.")

        text = text.replace(state_anchor, state_block, 1)

    loop_anchor = """                now = time.time()
                energy = audio_rms(data)
                is_voice = energy >= voice_threshold
"""

    if "LIVE INTERRUPT DETECTOR V2" not in text:
        detector = """                now = time.time()

                # === LIVE INTERRUPT DETECTOR V2 ===
                # While Jarvis is talking, don't wait for the normal silence-
                # based utterance detector. Keep a short rolling mic window and
                # periodically ask Whisper whether the user said Jarvis stop/cancel.
                if speaking_now.is_set():
                    live_interrupt_chunks.append(data)
                    live_interrupt_bytes += len(data)

                    bytes_per_second = max(1, int(AUDIO_SAMPLE_RATE) * 2)

                    max_bytes = int(bytes_per_second * LIVE_INTERRUPT_WINDOW_SECONDS)
                    while live_interrupt_chunks and live_interrupt_bytes > max_bytes:
                        removed = live_interrupt_chunks.pop(0)
                        live_interrupt_bytes -= len(removed)

                    buffered_seconds = live_interrupt_bytes / float(bytes_per_second)

                    if (
                        buffered_seconds >= LIVE_INTERRUPT_MIN_SECONDS
                        and (now - last_live_interrupt_check) >= LIVE_INTERRUPT_CHECK_INTERVAL
                    ):
                        last_live_interrupt_check = now

                        try:
                            interrupt_audio = b"".join(live_interrupt_chunks)
                            interrupt_text = transcribe_with_whisper(interrupt_audio)

                            if is_live_voice_interrupt_text(interrupt_text):
                                log_user_text("Heard live interrupt", interrupt_text)

                                try:
                                    stop_all_current_work()
                                except Exception:
                                    stop_current_speech()

                                live_interrupt_chunks = []
                                live_interrupt_bytes = 0
                                clear_mic_queue()
                                recording_active = False
                                chunks = []
                                pre_roll.clear()
                                started_while_jarvis_was_speaking = False
                                continue

                        except Exception as e:
                            log(f"Live interrupt check failed: {e}")

                    # Do not feed Jarvis's own TTS into the normal utterance VAD.
                    continue

                if live_interrupt_chunks:
                    live_interrupt_chunks = []
                    live_interrupt_bytes = 0

                energy = audio_rms(data)
                is_voice = energy >= voice_threshold
"""

        if loop_anchor not in text:
            raise RuntimeError("Could not find voice listener audio/VAD anchor.")

        text = text.replace(loop_anchor, detector, 1)

    old_process = """    if is_stop_talking_command(command):
        stop_current_speech()
        deactivate_conversation_mode()
        return
"""

    new_process = """    if is_stop_talking_command(command):
        try:
            stop_all_current_work()
        except Exception:
            stop_current_speech()
        deactivate_conversation_mode()
        return
"""

    if old_process in text:
        text = text.replace(old_process, new_process, 1)

    APP.write_text(text, encoding="utf-8")

    print("Jarvis Live Voice Interrupt V2 installed.")
    print("Backup:", backup_path)
    print()
    print('Say "Jarvis stop" or "Jarvis cancel" while he is speaking.')
    print()
    print("Now run:")
    print(r'cd C:\AI-Agent')
    print(r'.\venv\Scripts\python.exe -m py_compile .\jarvis_app.py')
    print(r'.\venv\Scripts\python.exe .\jarvis_app_v2.py')


if __name__ == "__main__":
    main()
