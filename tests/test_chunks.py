import numpy as np
import pytest

from rstrends.chunks import ChunkLedger, chunk_windows, run_resumable


def test_windows_cover_grid_exactly_once():
    h, w, size = 1000, 700, 256
    cover = np.zeros((h, w), dtype=int)
    for win in chunk_windows(h, w, size):
        cover[win.row_off : win.row_off + win.height, win.col_off : win.col_off + win.width] += 1
    assert (cover == 1).all()


def test_edge_windows_are_clipped():
    wins = chunk_windows(10, 10, 4)
    assert len(wins) == 9
    assert wins[-1].height == 2 and wins[-1].width == 2


def test_invalid_size_rejected():
    with pytest.raises(ValueError):
        chunk_windows(10, 10, 0)


def test_ledger_marks_atomically(tmp_path):
    ledger = ChunkLedger(tmp_path / "ledger")
    assert not ledger.is_done("r0_c0")
    ledger.mark_done("r0_c0", {"n": 5})
    assert ledger.is_done("r0_c0")
    assert not list((tmp_path / "ledger").glob("*.tmp"))


def test_resume_skips_finished_windows_and_retries_failed(tmp_path):
    wins = chunk_windows(8, 8, 4)  # 4 windows
    ledger = ChunkLedger(tmp_path / "ledger")
    seen = []

    def crash_on_third(win):
        if len(seen) == 2:
            raise RuntimeError("simulated crash")
        seen.append(win.key)

    with pytest.raises(RuntimeError):
        run_resumable(wins, crash_on_third, ledger)
    assert ledger.done_keys() == set(seen)  # the failed window was not marked

    rerun = []
    result = run_resumable(wins, lambda win: rerun.append(win.key), ledger)
    assert result == {"ran": 2, "skipped": 2}
    assert set(rerun).isdisjoint(seen)
    assert len(ledger.done_keys()) == 4
