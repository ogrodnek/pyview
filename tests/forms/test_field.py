"""Tests for FormField class."""

from datetime import date
from typing import Optional

import pytest
from pydantic import BaseModel, Field

from pyview.changesets import change_set
from pyview.forms import FormField


class TestFormFieldBasic:
    """Test basic FormField properties."""

    def test_create_simple_field(self):
        field = FormField(
            name="email",
            value="test@example.com",
            errors=(),
            field_info=None,
            annotation=str,
        )
        assert field.name == "email"
        assert field.value == "test@example.com"
        assert field.errors == ()

    def test_field_is_frozen(self):
        field = FormField(name="email", value="test", errors=())
        with pytest.raises(Exception):  # FrozenInstanceError
            field.name = "other"  # type: ignore

    def test_with_value_creates_new_field(self):
        field = FormField(name="email", value="old", errors=())
        new_field = field.with_value("new")
        assert field.value == "old"
        assert new_field.value == "new"
        assert new_field.name == field.name

    def test_with_errors_creates_new_field(self):
        field = FormField(name="email", value="test", errors=())
        new_field = field.with_errors(("Error 1", "Error 2"))
        assert field.errors == ()
        assert new_field.errors == ("Error 1", "Error 2")


class TestFormFieldId:
    """Test id property."""

    def test_simple_name(self):
        field = FormField(name="email", value="", errors=())
        assert field.id == "email"

    def test_nested_name(self):
        field = FormField(name="address.city", value="", errors=())
        assert field.id == "address_city"

    def test_deeply_nested(self):
        field = FormField(name="user.address.city", value="", errors=())
        assert field.id == "user_address_city"

    def test_with_list_index(self):
        field = FormField(name="tags.0", value="", errors=())
        assert field.id == "tags_0"

    def test_with_brackets(self):
        field = FormField(name="tags[0]", value="", errors=())
        assert field.id == "tags_0"


class TestFormFieldLabel:
    """Test label property."""

    def test_simple_name(self):
        field = FormField(name="email", value="", errors=())
        assert field.label == "Email"

    def test_underscored_name(self):
        field = FormField(name="first_name", value="", errors=())
        assert field.label == "First Name"

    def test_nested_uses_last_segment(self):
        field = FormField(name="address.city", value="", errors=())
        assert field.label == "City"

    def test_nested_underscored(self):
        field = FormField(name="address.zip_code", value="", errors=())
        assert field.label == "Zip Code"

    def test_title_from_field_info(self):
        class Model(BaseModel):
            email: str = Field(title="Email Address")

        field_info = Model.model_fields["email"]
        field = FormField(name="email", value="", errors=(), field_info=field_info)
        assert field.label == "Email Address"

    def test_list_index_uses_parent_name(self):
        field = FormField(name="tags.0", value="", errors=())
        assert field.label == "Tags"


class TestFormFieldErrors:
    """Test error-related properties."""

    def test_has_errors_false(self):
        field = FormField(name="email", value="", errors=())
        assert field.has_errors is False

    def test_has_errors_true(self):
        field = FormField(name="email", value="", errors=("Invalid email",))
        assert field.has_errors is True

    def test_first_error_none(self):
        field = FormField(name="email", value="", errors=())
        assert field.first_error is None

    def test_first_error_single(self):
        field = FormField(name="email", value="", errors=("Invalid email",))
        assert field.first_error == "Invalid email"

    def test_first_error_multiple(self):
        field = FormField(
            name="email", value="", errors=("Error 1", "Error 2", "Error 3")
        )
        assert field.first_error == "Error 1"


class TestFormFieldMetadata:
    """Test metadata-related properties."""

    def test_placeholder_none(self):
        field = FormField(name="email", value="", errors=())
        assert field.placeholder is None

    def test_placeholder_from_field_info(self):
        class Model(BaseModel):
            email: str = Field(json_schema_extra={"placeholder": "you@example.com"})

        field_info = Model.model_fields["email"]
        field = FormField(name="email", value="", errors=(), field_info=field_info)
        assert field.placeholder == "you@example.com"

    def test_description_none(self):
        field = FormField(name="email", value="", errors=())
        assert field.description is None

    def test_description_from_field_info(self):
        class Model(BaseModel):
            email: str = Field(description="Your email address")

        field_info = Model.model_fields["email"]
        field = FormField(name="email", value="", errors=(), field_info=field_info)
        assert field.description == "Your email address"


class TestFormFieldInputType:
    """Test input_type inference."""

    def test_default_text(self):
        field = FormField(name="foo", value="", errors=())
        assert field.input_type == "text"

    def test_email_from_name(self):
        field = FormField(name="email", value="", errors=(), annotation=str)
        assert field.input_type == "email"

    def test_number_from_annotation(self):
        field = FormField(name="count", value="", errors=(), annotation=int)
        assert field.input_type == "number"

    def test_checkbox_from_bool(self):
        field = FormField(name="is_active", value="", errors=(), annotation=bool)
        assert field.input_type == "checkbox"

    def test_date_from_annotation(self):
        field = FormField(name="birth_date", value="", errors=(), annotation=date)
        assert field.input_type == "date"


class TestFormFieldConstraints:
    """Test constraints property."""

    def test_no_constraints(self):
        field = FormField(name="name", value="", errors=())
        assert field.constraints == {}

    def test_constraints_from_field_info(self):
        class Model(BaseModel):
            name: str = Field(min_length=3, max_length=20)

        field_info = Model.model_fields["name"]
        field = FormField(name="name", value="", errors=(), field_info=field_info)
        constraints = field.constraints
        assert constraints["minlength"] == 3
        assert constraints["maxlength"] == 20


class TestFormFieldRequired:
    """Test required property."""

    def test_required_when_no_default(self):
        class Model(BaseModel):
            name: str

        field_info = Model.model_fields["name"]
        field = FormField(
            name="name", value="", errors=(), field_info=field_info, annotation=str
        )
        assert field.required is True

    def test_not_required_with_default(self):
        class Model(BaseModel):
            name: str = "default"

        field_info = Model.model_fields["name"]
        field = FormField(
            name="name", value="", errors=(), field_info=field_info, annotation=str
        )
        assert field.required is False

    def test_not_required_when_optional(self):
        class Model(BaseModel):
            name: Optional[str] = None

        field_info = Model.model_fields["name"]
        field = FormField(
            name="name",
            value="",
            errors=(),
            field_info=field_info,
            annotation=Optional[str],
        )
        assert field.required is False

    def test_required_unknown_without_field_info(self):
        field = FormField(name="name", value="", errors=())
        assert field.required is False  # Conservative default


class TestChangeSetFieldMethod:
    """Test ChangeSet.field() integration."""

    def test_field_method_returns_formfield(self):
        class User(BaseModel):
            name: str
            email: str

        cs = change_set(User, {"name": "John", "email": "john@example.com"})
        field = cs.field("name")

        assert isinstance(field, FormField)
        assert field.name == "name"
        assert field.value == "John"

    def test_field_method_includes_errors(self):
        class User(BaseModel):
            name: str = Field(min_length=3)

        cs = change_set(User)
        cs.apply({"name": ["Jo"], "_target": ["name"]})  # Too short

        field = cs.field("name")
        assert field.has_errors is True
        assert "at least 3" in field.first_error.lower()

    def test_field_method_nested(self):
        class Address(BaseModel):
            city: str

        class User(BaseModel):
            address: Address

        cs = change_set(User)
        cs.apply({"address.city": ["NYC"], "_target": ["address", "city"]})

        field = cs.field("address.city")
        assert field.value == "NYC"
        assert field.label == "City"

    def test_field_method_with_annotation(self):
        class User(BaseModel):
            age: int

        cs = change_set(User, {"age": 25})
        field = cs.field("age")

        assert field.annotation is int
        assert field.input_type == "number"

    def test_field_method_missing_field(self):
        class User(BaseModel):
            name: str

        cs = change_set(User)
        field = cs.field("nonexistent")

        # Should still return a FormField, just with no metadata
        assert field.name == "nonexistent"
        assert field.value == ""
        assert field.field_info is None
