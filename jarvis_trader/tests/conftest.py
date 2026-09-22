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
"""
import pytest

from jarvis_trader.security import credentials


@pytest.fixture
def isolated_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "CONFIG_PATH", tmp_path / "test_credentials.json")
    yield
