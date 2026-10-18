"""The running log's capture: what the semantics of "this thread's output, and
no one else's" have to be, which a journey can only show by accident."""

import threading

from tracebi.pipeline import runlog


def test_capture_sees_this_threads_prints_and_not_another_threads(capsys):
    seen = []
    other_done = threading.Event()

    def elsewhere():
        print("from another thread")
        other_done.set()

    with runlog.capture(seen.append):
        print("mine")
        threading.Thread(target=elsewhere).start()
        other_done.wait(5)
    assert "".join(seen) == "mine\n"
    # ...and it still reached the terminal, which is where it was going.
    assert "mine" in capsys.readouterr().out


def test_a_chatty_script_cannot_fill_the_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(runlog.RunLog, "MAX_BYTES", 200)
    log = runlog.RunLog(str(tmp_path / "1.log"))
    for i in range(100):
        log.line(f"row {i}")
    log.close()
    text, _ = runlog.read_from(log.path)
    assert len(text) < 400 and text.rstrip().endswith("[log full: output stops here]")
