"""Tests for form type inference utilities."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

import pytest
from pydantic import BaseModel, Field

from pyview.forms.types import get_field_constraints, infer_input_type


class TestInferInputType:
    """Test input type inference from field metadata."""

    def test_default_is_text(self):
        assert infer_input_type("foo") == "text"
        assert infer_input_type("bar", str) == "text"

    def test_int_becomes_number(self):
        assert infer_input_type("count", int) == "number"

    def test_float_becomes_number(self):
        assert infer_input_type("price", float) == "number"

    def test_decimal_becomes_number(self):
        assert infer_input_type("amount", Decimal) == "number"

    def test_bool_becomes_checkbox(self):
        assert infer_input_type("is_active", bool) == "checkbox"

    def test_date_becomes_date(self):
        assert infer_input_type("birth_date", date) == "date"

    def test_datetime_becomes_datetime_local(self):
        assert infer_input_type("created_at", datetime) == "datetime-local"

    def test_time_becomes_time(self):
        assert infer_input_type("start_time", time) == "time"

    def test_optional_int_becomes_number(self):
        assert infer_input_type("count", Optional[int]) == "number"

    def test_email_field_name(self):
        assert infer_input_type("email", str) == "email"
        assert infer_input_type("user_email", str) == "email"
        assert infer_input_type("email_address", str) == "email"

    def test_password_field_name(self):
        assert infer_input_type("password", str) == "password"
        assert infer_input_type("password_confirm", str) == "password"

    def test_phone_field_name(self):
        assert infer_input_type("phone", str) == "tel"
        assert infer_input_type("phone_number", str) == "tel"
        assert infer_input_type("telephone", str) == "tel"

    def test_url_field_name(self):
        assert infer_input_type("url", str) == "url"
        assert infer_input_type("website", str) == "url"
        assert infer_input_type("website_url", str) == "url"

    def test_search_field_name(self):
        assert infer_input_type("search", str) == "search"
        assert infer_input_type("search_query", str) == "search"

    def test_explicit_input_type_in_field_info(self):
        """Test that explicit input_type in json_schema_extra takes priority."""

        class Model(BaseModel):
            custom: str = Field(json_schema_extra={"input_type": "hidden"})

        field_info = Model.model_fields["custom"]
        assert infer_input_type("custom", str, field_info) == "hidden"

    def test_field_name_priority_over_type(self):
        # email in name should override int type
        assert infer_input_type("email_count", int) == "email"


class TestGetFieldConstraints:
    """Test extraction of HTML constraints from Pydantic FieldInfo."""

    def test_no_constraints(self):
        class Model(BaseModel):
            name: str

        field_info = Model.model_fields["name"]
        assert get_field_constraints(field_info) == {}

    def test_min_length(self):
        class Model(BaseModel):
            name: str = Field(min_length=3)

        field_info = Model.model_fields["name"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("minlength") == 3

    def test_max_length(self):
        class Model(BaseModel):
            name: str = Field(max_length=20)

        field_info = Model.model_fields["name"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("maxlength") == 20

    def test_min_max_length(self):
        class Model(BaseModel):
            name: str = Field(min_length=3, max_length=20)

        field_info = Model.model_fields["name"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("minlength") == 3
        assert constraints.get("maxlength") == 20

    def test_ge_constraint(self):
        class Model(BaseModel):
            age: int = Field(ge=0)

        field_info = Model.model_fields["age"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("min") == 0

    def test_le_constraint(self):
        class Model(BaseModel):
            age: int = Field(le=120)

        field_info = Model.model_fields["age"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("max") == 120

    def test_ge_le_constraints(self):
        class Model(BaseModel):
            rating: int = Field(ge=1, le=5)

        field_info = Model.model_fields["rating"]
        constraints = get_field_constraints(field_info)
        assert constraints.get("min") == 1
        assert constraints.get("max") == 5

    def test_none_field_info(self):
        assert get_field_constraints(None) == {}
