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
)
from http.server import ThreadingHTTPServer


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
