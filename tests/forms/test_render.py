"""The escape-hatch ladder, and the markup correctness the library owns."""

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, Field

from pyview.forms import Changeset, ui
from pyview.forms.render import (
    TAILWIND,
    Theme,
    control,
    error_summary,
    errors,
    input,
    render_form,
)


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
        assert 'id="prefs_name_error"' in html

    def test_overrides_win_over_inference(self, invalid):
        html = str(input(invalid.form.name, {"type": "password", "class": "mine"}))
        assert 'type="password"' in html and "mine" in html

    def test_a_class_override_merges_rather_than_replacing(self, invalid):
        html = str(input(invalid.form.name, {"class": "mine"}, TAILWIND))
        assert "mine" in html
        assert TAILWIND.control_invalid.split()[0] in html, (
            "replacing would silently turn off the theme's error styling"
        )

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

    def test_field_errors_are_not_assertive_live_regions(self, invalid):
        # pyview re-validates per keystroke and patches the DOM; role="alert"
        # here would re-announce on every patch and drown out the real one
        html = str(input(invalid.form.name))
        assert 'role="alert"' not in html

    def test_describedby_lists_the_hint_before_the_error(self):
        cs = Changeset(Prefs)
        cs.submit({"prefs": {"bio": "", "address": {"city": ""}}})
        cs.add_error("bio", "too dull")
        f = cs.form.bio
        assert f.describedby == f"{f.hint_id} {f.error_id}"
        assert f'id="{f.hint_id}"' in str(input(f))
        assert f'id="{f.error_id}"' in str(input(f))

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
        html = str(render_form(invalid, None, Theme()))
        assert 'class=""' in html, "the default theme contributes nothing"
        assert "text-red" not in html and "px-3" not in html

    def test_a_theme_supplies_every_class(self, invalid):
        html = str(input(invalid.form.name, None, TAILWIND))
        assert TAILWIND.label in html
        assert TAILWIND.control_invalid.split()[0] in html, "invalid controls get the error style"


class TestMiddleRung:
    """Render most of the form, hand-write the rest."""

    def test_exclude_leaves_fields_for_you(self, invalid):
        html = str(render_form(invalid, {"exclude": ["name", "bio"]}))
        assert 'name="prefs[name]"' not in html
        assert 'name="prefs[bio]"' not in html
        assert 'name="prefs[plan]"' in html

    def test_only_renders_what_you_asked_for(self, invalid):
        html = str(render_form(invalid, {"only": ["name"]}))
        assert 'name="prefs[name]"' in html
        assert 'name="prefs[plan]"' not in html


class TestErrorSummary:
    def test_nothing_before_a_submit_is_attempted(self):
        cs = Changeset(Prefs)
        cs.validate({"prefs": {"name": "x"}, "_target": ["prefs", "name"]})
        assert str(error_summary(cs)) == ""

    def test_links_point_at_the_inputs(self, invalid):
        html = str(error_summary(invalid))
        assert 'href="#prefs_name"' in html
        assert 'href="#prefs_address_city"' in html, "nested fields are linked too"

    def test_summary_text_matches_the_inline_message(self, invalid):
        summary = str(error_summary(invalid))
        inline = str(errors(invalid.form.name))
        # GOV.UK: the summary link and the field error must read identically,
        # or the user cannot tell they refer to the same problem
        assert "Name must be at least 3 characters." in summary
        assert "Name must be at least 3 characters." in inline

    def test_the_summary_is_the_one_thing_that_announces(self, invalid):
        assert 'role="alert"' in str(error_summary(invalid))
        assert 'role="alert"' not in str(input(invalid.form.name))

    def test_it_is_focusable_so_it_can_be_moved_to(self, invalid):
        assert 'tabindex="-1"' in str(error_summary(invalid))
