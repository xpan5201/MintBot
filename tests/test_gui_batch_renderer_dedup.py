import pytest


def _get_qapp():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app
    try:
        return QApplication([])
    except Exception as exc:
        pytest.skip(f"Qt QApplication not available: {exc!r}")


def test_batch_renderer_deduplicates_bound_method_callbacks():
    _get_qapp()
    from src.gui.performance_optimizer import BatchRenderer

    renderer = BatchRenderer(interval_ms=9999)

    class _Recorder:
        def __init__(self):
            self.calls = 0

        def cb(self) -> None:
            self.calls += 1

    rec = _Recorder()

    for _ in range(20):
        renderer.schedule_update(rec.cb)

    renderer._flush_updates()
    assert rec.calls == 1


def test_batch_renderer_allows_reschedule_from_inside_callback():
    _get_qapp()
    from src.gui.performance_optimizer import BatchRenderer

    renderer = BatchRenderer(interval_ms=9999)
    calls: list[str] = []

    def cb() -> None:
        calls.append("run")
        if len(calls) == 1:
            renderer.schedule_update(cb)

    renderer.schedule_update(cb)
    renderer._flush_updates()
    assert calls == ["run"]

    renderer._flush_updates()
    assert calls == ["run", "run"]
