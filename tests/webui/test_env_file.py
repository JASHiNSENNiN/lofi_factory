"""The Settings page's .env writer must round-trip any value the way the
pipeline (python-dotenv) reads it, atomically, and keep the file private."""
import os
import stat

import pytest
from dotenv import dotenv_values

from webui import config


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# keep me\nA=1\nWEBUI_PASSWORD=old\n")
    monkeypatch.setattr(config, "ENV_FILE", str(path))
    return path


@pytest.mark.parametrize("value", ["abc #1", 'pa"ss\\word', "with space", "it's", "plain", ""])
def test_values_round_trip_through_dotenv(env_file, value):
    config.write_env_value("WEBUI_PASSWORD", value)
    assert dotenv_values(env_file)["WEBUI_PASSWORD"] == value
    assert config.read_env_file()["WEBUI_PASSWORD"] == value


def test_other_lines_are_preserved_and_file_is_private(env_file):
    config.write_env_value("NEW_KEY", "x")
    text = env_file.read_text()
    assert "# keep me" in text and "A=1" in text and "NEW_KEY=x" in text
    assert stat.S_IMODE(os.stat(env_file).st_mode) == 0o600


def test_newlines_are_rejected(env_file):
    with pytest.raises(ValueError):
        config.write_env_value("A", "1\nEVIL=2")
