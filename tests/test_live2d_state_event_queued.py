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


def test_live2d_state_event_request_is_queued():
    app = _get_qapp()

    from src.gui.live2d_gl_widget import Live2DGlWidget

    try:
        widget = Live2DGlWidget()
    except Exception as exc:
        pytest.skip(f"Live2DGlWidget init failed: {exc!r}")

    called: list[str] = []

    def fake_apply_state_event(*_args, **_kwargs):
        called.append("called")
        return True

    widget.apply_state_event = fake_apply_state_event  # type: ignore[method-assign]

    widget.request_state_event("happy", intensity=0.7, hold_s=None, source="test")
    assert called == []

    app.processEvents()
    assert called == ["called"]

    widget.deleteLater()
    app.processEvents()
