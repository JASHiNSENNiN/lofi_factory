from unittest.mock import patch

from scripts.composer import _BG_GEN_NICE_LEVEL, midi_to_wav


def _run(low_priority, os_name):
    with patch('subprocess.run') as mock_run, \
         patch('scripts.composer._pick_soundfont', return_value='sf.sf2'), \
         patch('os.name', os_name):
        midi_to_wav('in.mid', 'out.wav', soundfont='sf.sf2', low_priority=low_priority)
        return mock_run.call_args[0][0]


def test_low_priority_false_runs_fluidsynth_directly():
    cmd = _run(low_priority=False, os_name='posix')
    assert cmd[0] == 'fluidsynth'


def test_low_priority_true_on_posix_wraps_with_nice_and_ionice():
    cmd = _run(low_priority=True, os_name='posix')
    assert cmd[:5] == ['nice', '-n', str(_BG_GEN_NICE_LEVEL), 'ionice', '-c3']
    assert 'fluidsynth' in cmd


def test_low_priority_true_on_non_posix_still_runs_fluidsynth_directly():
    # nice/ionice don't exist on Windows -- must not prefix the command there.
    cmd = _run(low_priority=True, os_name='nt')
    assert cmd[0] == 'fluidsynth'


def test_default_low_priority_is_false():
    # Calling without low_priority at all -- must match the plain (non-nice)
    # path, i.e. the default preserves pre-existing callers' behavior.
    with patch('subprocess.run') as mock_run, \
         patch('scripts.composer._pick_soundfont', return_value='sf.sf2'), \
         patch('os.name', 'posix'):
        midi_to_wav('in.mid', 'out.wav', soundfont='sf.sf2')
        cmd = mock_run.call_args[0][0]
    assert cmd[0] == 'fluidsynth'


def test_fluidsynth_args_unchanged_by_low_priority_wrapping():
    plain = _run(low_priority=False, os_name='posix')
    wrapped = _run(low_priority=True, os_name='posix')
    # The actual fluidsynth invocation (everything from 'fluidsynth' onward)
    # must be identical either way -- only the priority prefix differs.
    fs_index = wrapped.index('fluidsynth')
    assert wrapped[fs_index:] == plain
