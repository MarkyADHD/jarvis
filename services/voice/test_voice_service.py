"""Real, runnable tests for the state machine + HTTP wiring, using
FakeAudioBackend so none of this needs a mic, speakers, or Whisper/Piper
installed. What FakeAudioBackend can't prove - real capture quality, real
transcription accuracy, real playback - is tracked as needs-your-PC in
docs/build-ledger.md, not claimed here.
"""

import json
import threading
import unittest
from http.client import HTTPConnection

from voice_service import (
    FakeAudioBackend,
    InvalidTransition,
    VoiceService,
    VoiceStateMachine,
    make_handler,
    resample_linear,
    resolve_input_device,
)
from http.server import ThreadingHTTPServer


class _FakeSoundDevice:
    """Stands in for the `sounddevice` module's query_devices/query_hostapis
    shape, using the real ambiguous device list found by hand on Marky's
    GoXLR-equipped PC - so this stays testable without real audio hardware.
    """

    _DEVICES = [
        {"name": "Chat Mic (TC-HELICON GoXLR Mini)", "max_input_channels": 2, "hostapi": 0},
        {"name": "Chat Mic (TC-HELICON GoXLR Mini)", "max_input_channels": 2, "hostapi": 1},
        {"name": "Chat Mic (TC-HELICON GoXLR Mini)", "max_input_channels": 2, "hostapi": 2},
        {"name": "Chat Mic (Chat Mic)", "max_input_channels": 2, "hostapi": 3},
        {"name": "Speakers (Realtek)", "max_input_channels": 0, "hostapi": 0},
        {"name": "Microphone (Realtek)", "max_input_channels": 2, "hostapi": 0},
    ]
    _HOSTAPIS = [
        {"name": "MME"},
        {"name": "Windows DirectSound"},
        {"name": "Windows WASAPI"},
        {"name": "Windows WDM-KS"},
    ]

    def query_devices(self, index=None, kind=None):  # noqa: ARG002 (kind unused, matches sd's signature shape)
        if index is None:
            return self._DEVICES
        return self._DEVICES[index]

    def query_hostapis(self):
        return self._HOSTAPIS


class ResolveInputDeviceTests(unittest.TestCase):
    def test_unambiguous_name_resolves_to_its_index(self):
        self.assertEqual(resolve_input_device(_FakeSoundDevice(), "Microphone (Realtek)"), 5)

    def test_ambiguous_name_prefers_wasapi(self):
        self.assertEqual(resolve_input_device(_FakeSoundDevice(), "Chat Mic"), 2)

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            resolve_input_device(_FakeSoundDevice(), "nonexistent device")

    def test_int_and_none_pass_through_unchanged(self):
        self.assertEqual(resolve_input_device(_FakeSoundDevice(), 3), 3)
        self.assertIsNone(resolve_input_device(_FakeSoundDevice(), None))


class ResampleTests(unittest.TestCase):
    """Pure numpy, no hardware - but real regression coverage for the bug
    found by hand on Marky's PC: his GoXLR mic only opens at 48kHz, so
    capture happens at the device's real rate and gets resampled down to
    what Whisper wants, not captured at 16kHz directly.
    """

    def test_resample_48k_to_16k_preserves_duration_and_roughly_the_signal(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed in this environment")

        src_rate, dst_rate = 48000, 16000
        duration_s = 0.5
        freq_hz = 440
        t = np.linspace(0, duration_s, int(src_rate * duration_s), endpoint=False)
        tone = np.sin(2 * np.pi * freq_hz * t).astype(np.float32)

        resampled = resample_linear(tone, src_rate, dst_rate)

        expected_len = int(dst_rate * duration_s)
        self.assertAlmostEqual(len(resampled), expected_len, delta=1)
        self.assertLessEqual(float(np.abs(resampled).max()), 1.01)  # no blow-up

    def test_resample_is_a_noop_when_rates_already_match(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed in this environment")

        audio = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        result = resample_linear(audio, 16000, 16000)
        np.testing.assert_array_equal(result, audio)

    def test_resample_handles_empty_audio(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed in this environment")

        result = resample_linear(np.array([], dtype=np.float32), 48000, 16000)
        self.assertEqual(len(result), 0)


class StateMachineTests(unittest.TestCase):
    def test_starts_dormant(self):
        self.assertEqual(VoiceStateMachine().state, "dormant")

    def test_legal_forward_path(self):
        m = VoiceStateMachine()
        for state in ["listening", "transcribing", "thinking", "speaking", "dormant"]:
            m.transition(state)
        self.assertEqual(m.state, "dormant")

    def test_illegal_jump_from_listening_to_speaking(self):
        m = VoiceStateMachine()
        m.transition("listening")
        with self.assertRaises(InvalidTransition):
            m.transition("speaking")

    def test_interrupt_and_error_always_legal(self):
        m = VoiceStateMachine()
        m.transition("listening")
        m.transition("interrupted")
        m.transition("listening")
        m.transition("transcribing")
        m.transition("error")
        m.transition("dormant")
        self.assertEqual(m.state, "dormant")

    def test_on_change_notified(self):
        events = []
        m = VoiceStateMachine(on_change=events.append)
        m.transition("listening", reason="ptt pressed")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].state, "listening")
        self.assertEqual(events[0].reason, "ptt pressed")


class VoiceServicePushToTalkTests(unittest.TestCase):
    def test_full_ptt_round_trip_returns_to_dormant_with_transcript(self):
        backend = FakeAudioBackend(fixed_transcript="hey jarvis what's the weather")
        service = VoiceService(backend)

        service.ptt_start()
        self.assertEqual(service.machine.state, "listening")
        self.assertTrue(backend.capturing)

        event, transcript = service.ptt_stop()
        self.assertEqual(event.state, "dormant")
        self.assertEqual(transcript, "hey jarvis what's the weather")
        self.assertFalse(backend.capturing)

    def test_speak_returns_to_dormant_and_calls_backend(self):
        backend = FakeAudioBackend()
        service = VoiceService(backend)
        service.speak("good evening sir")
        self.assertEqual(service.machine.state, "dormant")
        self.assertEqual(backend.spoken, ["good evening sir"])

    def test_speak_failure_lands_in_error_state_not_a_fake_success(self):
        class ExplodingBackend(FakeAudioBackend):
            def speak(self, text):
                raise RuntimeError("tts model not loaded")

        service = VoiceService(ExplodingBackend())
        with self.assertRaises(RuntimeError):
            service.speak("hello")
        self.assertEqual(service.machine.state, "error")

    def test_control_stop_returns_to_dormant(self):
        backend = FakeAudioBackend()
        service = VoiceService(backend)
        service.ptt_start()
        event = service.control("stop")
        self.assertEqual(event.state, "dormant")


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeAudioBackend(fixed_transcript="test transcript")
        self.service = VoiceService(self.backend)
        self.token = "test-token"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service, self.token))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _conn(self) -> HTTPConnection:
        return HTTPConnection("127.0.0.1", self.port)

    def test_rejects_without_token(self):
        conn = self._conn()
        conn.request("GET", "/state")
        res = conn.getresponse()
        self.assertEqual(res.status, 401)

    def test_full_round_trip_over_http(self):
        headers = {"X-Jarvis-Token": self.token}

        conn = self._conn()
        conn.request("POST", "/ptt/start", headers=headers)
        res = conn.getresponse()
        body = json.loads(res.read())
        self.assertEqual(res.status, 200)
        self.assertEqual(body["state"], "listening")
        conn.close()

        conn = self._conn()
        conn.request("POST", "/ptt/stop", headers=headers)
        res = conn.getresponse()
        body = json.loads(res.read())
        self.assertEqual(res.status, 200)
        self.assertEqual(body["state"], "dormant")
        self.assertEqual(body["transcript"], "test transcript")
        conn.close()

    def test_speak_endpoint_requires_text(self):
        conn = self._conn()
        conn.request(
            "POST", "/speak", body=json.dumps({}), headers={"X-Jarvis-Token": self.token, "Content-Type": "application/json"}
        )
        res = conn.getresponse()
        self.assertEqual(res.status, 400)


if __name__ == "__main__":
    unittest.main()
