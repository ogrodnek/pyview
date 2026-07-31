"""The escape-hatch ladder, and the markup correctness the library owns."""

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, Field

from pyview.forms import Changeset, ui
from pyview.forms.render import TAILWIND, Theme, control, input, render_form


class Address(BaseModel):
    city: str = Field(min_length=1)


class Prefs(BaseModel):
    name: str = Field(min_length=3)
    plan: Annotated[str, ui(widget="select", choices=[("free", "Free"), ("pro", "Pro")])] = "free"
    bio: Annotated[Optional[str], ui(widget="textarea", rows=3, help="Optional.")] = None
    subscribe: bool = False
    address: Address


@pytest.fixture
def invalid():
    cs = Changeset(Prefs)
    cs.submit({"prefs": {"name": "x", "plan": "pro", "subscribe": "true", "address": {"city": ""}}})
    return cs


class TestLadder:
    def test_whole_form(self, invalid):
        html = str(render_form(invalid))
        assert 'name="prefs[name]"' in html
        assert 'name="prefs[address][city]"' in html, "nested fields are included"
        assert "<fieldset" in html

    def test_one_field_includes_label_control_and_error(self, invalid):
        html = str(input(invalid.form.name))
        assert 'for="prefs_name"' in html and "<label" in html
        assert 'name="prefs[name]"' in html
        assert 'role="alert"' in html

    def test_overrides_win_over_inference(self, invalid):
        html = str(input(invalid.form.name, {"type": "password", "class": "mine"}))
        assert 'type="password"' in html and 'class="mine"' in html

    def test_bare_control_has_no_wrapper(self, invalid):
        html = str(control(invalid.form.name))
        assert html.startswith("<input") and "<label" not in html

    def test_hand_written_html_still_binds(self, invalid):
        f = invalid.form.address.city
        assert f.name == "prefs[address][city]"
        assert f.id == "prefs_address_city"
        assert f.value == ""
        assert f.errors


class TestMarkupCorrectness:
    def test_accessibility_wiring_is_emitted_by_default(self, invalid):
        html = str(input(invalid.form.name))
        assert 'aria-invalid="true"' in html
        assert 'aria-describedby="prefs_name_error"' in html
        assert 'id="prefs_name_error"' in html, "describedby must point at something real"

    def test_help_text_is_wired_too(self, invalid):
        html = str(input(invalid.form.bio))
        assert 'aria-describedby="prefs_bio_help"' in html
        assert 'id="prefs_bio_help"' in html

    def test_checkbox_emits_the_hidden_false_input(self, invalid):
        html = str(input(invalid.form.subscribe))
        assert '<input type="hidden" name="prefs[subscribe]" value="false"' in html, (
            "without this an unchecked box sends nothing and can never be cleared"
        )
        assert "checked" in html

    def test_select_marks_the_current_option(self, invalid):
        html = str(control(invalid.form.plan))
        assert '<option value="pro" selected>' in html

    def test_textarea_uses_a_body_not_a_value_attribute(self, invalid):
        html = str(control(invalid.form.bio))
        assert html.startswith("<textarea") and 'rows="3"' in html

    def test_values_are_escaped(self):
        cs = Changeset(Prefs)
        cs.validate({"prefs": {"name": '"><script>alert(1)</script>'}})
        html = str(control(cs.form.name))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestTheme:
    def test_no_style_classes_leak_from_the_library(self, invalid):
        html = str(render_form(invalid, Theme()))
        assert 'class=""' in html, "the default theme contributes nothing"
        assert "text-red" not in html and "px-3" not in html

    def test_a_theme_supplies_every_class(self, invalid):
        html = str(input(invalid.form.name, None, TAILWIND))
        assert TAILWIND.label in html
        assert TAILWIND.control_invalid.split()[0] in html, "invalid controls get the error style"
