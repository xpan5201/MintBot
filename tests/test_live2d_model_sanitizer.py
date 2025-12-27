from __future__ import annotations

import json
from pathlib import Path

from src.gui.live2d_gl_widget import _sanitize_model3_json_for_cubism


def _write_text(path: Path, text: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_live2d_sanitizer_preserves_motion_groups(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_text(model_dir / "model.moc3", "x")
    _write_text(model_dir / "tex.png", "x")
    _write_text(model_dir / "点头.motion3.json", "{}")
    _write_text(model_dir / "idle.motion3.json", "{}")

    model_json = model_dir / "model.model3.json"
    model_json.write_text(
        json.dumps(
            {
                "Version": 3,
                "FileReferences": {
                    "Moc": "model.moc3",
                    "Textures": ["tex.png"],
                    "Motions": {
                        "TapBody": [{"File": "点头.motion3.json"}],
                        "Idle": [{"File": "idle.motion3.json"}],
                    },
                },
                "Groups": [{"Target": "Parameter", "Name": "EyeBlink", "Ids": []}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out = _sanitize_model3_json_for_cubism(model_json, cache_base=tmp_path / "cache")
    assert out.exists()
    assert out != model_json

    out.read_bytes().decode("ascii")

    data = json.loads(out.read_text(encoding="utf-8"))
    motions = data["FileReferences"]["Motions"]
    assert "TapBody" in motions
    assert "Idle" in motions

    tap_file = motions["TapBody"][0]["File"]
    assert tap_file.startswith("motions/")
    assert (out.parent / tap_file).exists()


def test_live2d_sanitizer_adds_expressions_and_motions_when_missing(tmp_path: Path) -> None:
    model_dir = tmp_path / "model2"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_text(model_dir / "model.moc3", "x")
    _write_text(model_dir / "tex.png", "x")
    _write_text(model_dir / "哭哭.exp3.json", "{}")
    _write_text(model_dir / "待机动画.motion3.json", "{}")

    model_json = model_dir / "model.model3.json"
    model_json.write_text(
        json.dumps(
            {
                "Version": 3,
                "FileReferences": {"Moc": "model.moc3", "Textures": ["tex.png"]},
                "Groups": [{"Target": "Parameter", "Name": "LipSync", "Ids": []}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out = _sanitize_model3_json_for_cubism(model_json, cache_base=tmp_path / "cache")
    assert out.exists()
    out.read_bytes().decode("ascii")

    data = json.loads(out.read_text(encoding="utf-8"))
    refs = data["FileReferences"]
    assert "Expressions" in refs
    assert "Motions" in refs

    expr = refs["Expressions"][0]
    assert isinstance(expr.get("Name"), str) and expr["Name"]
    assert isinstance(expr.get("File"), str) and expr["File"].startswith("expressions/")
    assert (out.parent / expr["File"]).exists()

    motions = refs["Motions"]
    assert "Idle" in motions
    motion_file = motions["Idle"][0]["File"]
    assert motion_file.startswith("motions/")
    assert (out.parent / motion_file).exists()


def test_live2d_sanitizer_copies_core_assets_when_source_path_has_unicode(tmp_path: Path) -> None:
    model_dir = tmp_path / "模型"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_text(model_dir / "model.moc3", "x")
    _write_text(model_dir / "tex.png", "x")
    _write_text(model_dir / "表情.exp3.json", "{}")

    model_json = model_dir / "model.model3.json"
    model_json.write_text(
        json.dumps(
            {
                "Version": 3,
                "FileReferences": {"Moc": "model.moc3", "Textures": ["tex.png"]},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out = _sanitize_model3_json_for_cubism(model_json, cache_base=tmp_path / "cache")
    assert out.exists()
    out.read_bytes().decode("ascii")

    data = json.loads(out.read_text(encoding="utf-8"))
    refs = data["FileReferences"]
    assert ".." not in str(refs.get("Moc", ""))
    assert (out.parent / refs["Moc"]).exists()
