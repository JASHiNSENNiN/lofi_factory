"""File names and video IDs go into raw ui.html() markup; they must not be
able to close the attribute or inject markup."""
from webui.app import _src


def test_src_escapes_quotes_and_angle_brackets():
    out = _src("/videos/", 'a"><script>x</script>.mp4')
    assert '"' not in out and "<" not in out and ">" not in out
    assert out.startswith("/videos/")


def test_src_keeps_plain_names_readable():
    assert _src("/music/", "track_1_02.wav") == "/music/track_1_02.wav"


def test_src_cannot_climb_directories():
    assert "/" not in _src("/media/", "../.env")[len("/media/"):]
