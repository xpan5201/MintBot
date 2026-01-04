from __future__ import annotations


from src.gui.live2d_state_event import (
    extract_explicit_state_directive,
    filter_explicit_state_directives_stream,
)


def test_extract_explicit_state_directive_basic() -> None:
    cleaned, directive = extract_explicit_state_directive("Hello [[live2d:angry]] world")
    assert cleaned == "Hello world"
    assert directive == ("angry", None, None)


def test_extract_explicit_state_directive_last_wins() -> None:
    cleaned, directive = extract_explicit_state_directive(
        "a [[live2d:angry]] b [[live2d:shy|0.5]] c"
    )
    assert cleaned == "a b c"
    assert directive == ("shy", 0.5, None)


def test_extract_explicit_state_directive_intensity_and_hold() -> None:
    cleaned, directive = extract_explicit_state_directive("[[live2d:猫尾|0.8|3]]")
    assert cleaned == ""
    assert directive == ("猫尾", 0.8, 3.0)


def test_extract_explicit_state_directive_json_basic() -> None:
    cleaned, directive = extract_explicit_state_directive(
        'Hello [[live2d:{"event":"angry"}]] world'
    )
    assert cleaned == "Hello world"
    assert directive == ("angry", None, None)


def test_extract_explicit_state_directive_json_intensity_and_hold() -> None:
    cleaned, directive = extract_explicit_state_directive(
        '[[live2d:{"event":"猫尾","intensity":0.8,"hold_s":3}]]'
    )
    assert cleaned == ""
    assert directive == ("猫尾", 0.8, 3.0)


def test_extract_explicit_state_directive_single_bracket_compat() -> None:
    cleaned, directive = extract_explicit_state_directive("Hello [live2d:angry] world")
    assert cleaned == "Hello world"
    assert directive == ("angry", None, None)


def test_extract_explicit_state_directive_json_single_bracket_compat() -> None:
    cleaned, directive = extract_explicit_state_directive(
        'Hello [live2d:{"event":"happy","intensity":0.8,"hold_s":3}] world'
    )
    assert cleaned == "Hello world"
    assert directive == ("happy", 0.8, 3.0)


def test_extract_explicit_state_directive_incomplete_dropped() -> None:
    cleaned, directive = extract_explicit_state_directive("a [[live2d:angry")
    assert cleaned == "a [[live2d:angry"
    assert directive is None


def test_filter_explicit_state_directives_stream_boundary_split() -> None:
    buf = ""
    out1, buf, directive1 = filter_explicit_state_directives_stream(buf, "Hello [[live2")
    assert out1 == "Hello "
    assert directive1 is None
    assert buf == "[[live2"

    out2, buf, directive2 = filter_explicit_state_directives_stream(buf, "d:angry]] world")
    assert out2 == " world"
    assert buf == ""
    assert directive2 == ("angry", None, None)


def test_filter_explicit_state_directives_stream_json_boundary_split() -> None:
    buf = ""
    out1, buf, directive1 = filter_explicit_state_directives_stream(
        buf, 'Hello [[live2d:{"event":"angry"'
    )
    assert out1 == "Hello "
    assert directive1 is None
    assert buf == '[[live2d:{"event":"angry"'

    out2, buf, directive2 = filter_explicit_state_directives_stream(buf, "}]] world")
    assert out2 == " world"
    assert buf == ""
    assert directive2 == ("angry", None, None)


def test_filter_explicit_state_directives_stream_single_bracket_boundary_split() -> None:
    buf = ""
    out1, buf, directive1 = filter_explicit_state_directives_stream(buf, "Hello [live2")
    assert out1 == "Hello "
    assert directive1 is None
    assert buf == "[live2"

    out2, buf, directive2 = filter_explicit_state_directives_stream(buf, "d:angry] world")
    assert out2 == " world"
    assert buf == ""
    assert directive2 == ("angry", None, None)


def test_filter_explicit_state_directives_stream_json_single_bracket_boundary_split() -> None:
    buf = ""
    out1, buf, directive1 = filter_explicit_state_directives_stream(
        buf, 'Hello [live2d:{"event":"angry"'
    )
    assert out1 == "Hello "
    assert directive1 is None
    assert buf == '[live2d:{"event":"angry"'

    out2, buf, directive2 = filter_explicit_state_directives_stream(buf, "}] world")
    assert out2 == " world"
    assert buf == ""
    assert directive2 == ("angry", None, None)
