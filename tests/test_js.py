import json

import pytest

from pyview.js import _format_transition, js

# _format_transition


def test_format_transition_simple_string():
    assert _format_transition("fade-in") == [["fade-in"], [], []]


def test_format_transition_splits_spaces():
    assert _format_transition("transition-all duration-300 ease-out") == [
        ["transition-all", "duration-300", "ease-out"],
        [],
        [],
    ]


def test_format_transition_3_tuple_strings():
    result = _format_transition(
        ("transition-all duration-300", "opacity-0 scale-95", "opacity-100 scale-100")
    )
    assert result == [
        ["transition-all", "duration-300"],
        ["opacity-0", "scale-95"],
        ["opacity-100", "scale-100"],
    ]


def test_format_transition_3_tuple_lists():
    result = _format_transition((["transition-all"], ["opacity-0"], ["opacity-100"]))
    assert result == [["transition-all"], ["opacity-0"], ["opacity-100"]]


def test_format_transition_invalid_raises():
    with pytest.raises(ValueError):
        _format_transition(("a", "b"))  # type: ignore[arg-type]


# Serialization


def test_show_serializes_to_phoenix_format():
    result = json.loads(str(js.show("#modal")))
    assert result == [["show", {"to": "#modal"}]]


def test_hide_with_transition_serializes():
    result = json.loads(str(js.hide("#el", transition="fade-out", time=300)))
    assert result == [["hide", {"to": "#el", "transition": [["fade-out"], [], []], "time": 300}]]


def test_push_with_value_serializes():
    result = json.loads(str(js.push("delete", value={"id": 123})))
    assert result == [["push", {"event": "delete", "value": {"id": 123}}]]


def test_dispatch_serializes():
    result = json.loads(str(js.dispatch("copy", to="#text")))
    assert result == [["dispatch", {"event": "copy", "to": "#text"}]]


def test_add_class_single_string():
    result = json.loads(str(js.add_class("active", to="#el")))
    assert result == [["add_class", {"names": ["active"], "to": "#el"}]]


def test_add_class_list():
    result = json.loads(str(js.add_class(["a", "b"], to="#el")))
    assert result == [["add_class", {"names": ["a", "b"], "to": "#el"}]]


def test_set_attribute_tuple():
    result = json.loads(str(js.set_attribute(("disabled", "true"), to="#btn")))
    assert result == [["set_attr", {"attr": ["disabled", "true"], "to": "#btn"}]]


def test_toggle_attribute_3_tuple():
    result = json.loads(str(js.toggle_attribute(("aria-pressed", "true", "false"), to="#btn")))
    assert result == [["toggle_attr", {"attr": ["aria-pressed", "true", "false"], "to": "#btn"}]]


# Optional params excluded when not set


def test_show_no_to_when_omitted():
    result = json.loads(str(js.show()))
    assert result == [["show", {}]]


def test_dispatch_no_bubbles_when_true():
    result = json.loads(str(js.dispatch("ev")))
    assert result == [["dispatch", {"event": "ev"}]]


def test_dispatch_bubbles_false_included():
    result = json.loads(str(js.dispatch("ev", bubbles=False)))
    assert result == [["dispatch", {"event": "ev", "bubbles": False}]]


def test_show_blocking_false_included():
    result = json.loads(str(js.show("#el", blocking=False)))
    assert result == [["show", {"to": "#el", "blocking": False}]]


# Chaining


def test_chaining_produces_multiple_commands():
    result = json.loads(str(js.show("#modal").push("opened")))
    assert result == [
        ["show", {"to": "#modal"}],
        ["push", {"event": "opened"}],
    ]


def test_chaining_is_immutable():
    a = js.show("#el")
    b = a.push("event")
    assert len(json.loads(str(a))) == 1
    assert len(json.loads(str(b))) == 2


def test_three_command_chain():
    result = json.loads(
        str(
            js.hide("#item", transition="fade-out")
            .push("delete", value={"id": 1})
            .dispatch("deleted", to="#list")
        )
    )
    assert len(result) == 3
    assert result[0][0] == "hide"
    assert result[1][0] == "push"
    assert result[2][0] == "dispatch"


# __html__ matches __str__


def test_html_matches_str():
    cmd = js.show("#el").push("event")
    assert cmd.__html__() == str(cmd)
