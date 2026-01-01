import json
import os
from pathlib import Path

import pytest


def test_live2d_expression_cache_refresh_uses_mtime(temp_dir, monkeypatch) -> None:
    from src.gui.live2d_gl_widget import Live2DGlWidget

    model_dir = temp_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_json = model_dir / "test.model3.json"
    exp_file = model_dir / "happy.exp3.json"
    exp_file.write_text("{}", encoding="utf-8")
    model_json.write_text(
        json.dumps(
            {
                "FileReferences": {
                    "Expressions": [
                        {
                            "File": exp_file.name,
                            "Name": "happy",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    widget = Live2DGlWidget.__new__(Live2DGlWidget)
    widget._model_json = model_json  # type: ignore[attr-defined]
    widget._expr_files_cache_dir = None  # type: ignore[attr-defined]
    widget._expr_files_cache_mtime = 0.0  # type: ignore[attr-defined]
    widget._expr_files_cache_dir_mtime = 0.0  # type: ignore[attr-defined]
    widget._expr_files_cache_model_json_mtime = 0.0  # type: ignore[attr-defined]
    widget._expr_files_cache = []  # type: ignore[attr-defined]
    widget._expr_candidates_cache = {}  # type: ignore[attr-defined]

    model_json_content = model_json.read_text(encoding="utf-8")

    read_calls = 0
    glob_calls = 0
    orig_read_text = Path.read_text
    orig_glob = Path.glob

    def counting_read_text(self, *args, **kwargs):  # noqa: ANN001
        nonlocal read_calls
        read_calls += 1
        return orig_read_text(self, *args, **kwargs)

    def counting_glob(self, pattern):  # noqa: ANN001
        nonlocal glob_calls
        glob_calls += 1
        return orig_glob(self, pattern)

    monkeypatch.setattr(Path, "read_text", counting_read_text, raising=True)
    monkeypatch.setattr(Path, "glob", counting_glob, raising=True)

    widget._refresh_expression_cache()
    first = (read_calls, glob_calls)

    widget._refresh_expression_cache()
    assert (read_calls, glob_calls) == first

    # Touch model3.json to change its mtime; cache should refresh.
    model_json.write_text(model_json_content, encoding="utf-8")
    try:
        bumped = float(model_json.stat().st_mtime) + 5.0
        os.utime(model_json, (bumped, bumped))
    except Exception:
        # If utime fails (rare), the test may become flaky on coarse mtime resolution.
        pytest.skip("os.utime failed; cannot reliably bump mtime for this platform")
    widget._refresh_expression_cache()

    assert read_calls > first[0]
    assert glob_calls > first[1]
