"""
Shared pytest fixtures for the JarvisTrader test suite.

isolated_credentials is mandatory for ANY test that calls
credentials.save_api_credentials()/delete_credentials() -- a real
incident during this project's own development proved why: a test's
setup/teardown wrote fake values into the real demo/live slots of the
actual C:\\AI-Agent\\JarvisMemory\\jarvis_trader\\credentials.json file
and then deleted those slots at teardown, destroying the user's real,
already-connected Trading 212 API credentials (both demo and live) in
the process. Tests must NEVER touch that real file, ever -- this
fixture redirects credentials.CONFIG_PATH to a throwaway temp file for
the duration of the test, so nothing a test does can reach the real
credential store no matter what it saves or deletes.

isolated_scheduler and isolated_kill_switch exist for the exact same
reason, against the exact same class of bug: a SECOND real incident
happened when a manual cleanup script called scheduler.stop() to reset
test state, which silently paused the user's actual, currently-running
autonomous demo trading loop (scheduler.STATE_FILE is the same real
file a live jarvistrader_server.py process reads/writes -- there was
never a test/production split). kill_switch.KILL_SWITCH_FILE is the
exact same shared-file pattern and carries a real safety implication
if a test run were to momentarily disengage a live kill switch, so it
gets the same isolation even though no incident has (yet) come from it.
"""
import pytest

from jarvis_trader.core import kill_switch, scheduler
from jarvis_trader.security import credentials


@pytest.fixture
def isolated_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "CONFIG_PATH", tmp_path / "test_credentials.json")
    yield


@pytest.fixture
def isolated_scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "STATE_FILE", tmp_path / "test_demo_trading_state.json")
    yield


@pytest.fixture
def isolated_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_FILE", tmp_path / "test_kill_switch.json")
    yield
