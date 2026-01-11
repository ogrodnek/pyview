"""Tests for ChangeSet functionality."""

from typing import Optional

import pytest
from pydantic import BaseModel, Field, model_validator


from pyview.changesets import ChangeSet, change_set


# Test models
class SimpleUser(BaseModel):
    name: str = Field(min_length=2)
    email: str


class Address(BaseModel):
    street: str
    city: str = Field(min_length=2)
    zip_code: Optional[str] = None


class UserWithAddress(BaseModel):
    name: str
    address: Address


class UserWithTags(BaseModel):
    name: str
    tags: list[str] = []


class UserWithAddresses(BaseModel):
    name: str
    addresses: list[Address] = []


class UserWithPasswordConfirm(BaseModel):
    username: str
    password: str
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class TestChangeSetBasic:
    """Test basic ChangeSet functionality (backward compatibility)."""

    def test_create_empty_changeset(self):
        cs = change_set(SimpleUser)
        assert cs.cls is SimpleUser
        assert cs.changes == {}
        assert cs.errors == {}
        assert cs.valid is False

    def test_create_with_initial_values(self):
        cs = change_set(SimpleUser, {"name": "John", "email": "john@example.com"})
        assert cs.changes == {"name": "John", "email": "john@example.com"}

    def test_getitem_flat(self):
        cs = change_set(SimpleUser, {"name": "John"})
        assert cs["name"] == "John"
        assert cs["email"] == ""  # Missing returns empty string

    def test_fields_property(self):
        cs = change_set(SimpleUser)
        assert set(cs.fields) == {"name", "email"}

    def test_attrs_property(self):
        cs = change_set(SimpleUser, {"name": "John", "email": "j@example.com"})
        attrs = cs.attrs
        assert attrs.name == "John"
        assert attrs.email == "j@example.com"

    def test_model_property_valid(self):
        cs = change_set(SimpleUser, {"name": "John", "email": "j@example.com"})
        model = cs.model
        assert model is not None
        assert model.name == "John"
        assert model.email == "j@example.com"

    def test_model_property_invalid(self):
        cs = change_set(SimpleUser, {"name": "J"})  # Too short, missing email
        assert cs.model is None


class TestChangeSetApply:
    """Test apply() method for real-time validation."""

    def test_apply_flat_field(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["John"], "_target": ["name"]})
        assert cs["name"] == "John"
        assert cs.action == "validate"

    def test_apply_updates_changes(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["John"], "_target": ["name"]})
        cs.apply({"email": ["j@example.com"], "_target": ["email"]})
        assert cs.changes == {"name": "John", "email": "j@example.com"}

    def test_apply_validates(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["John"], "_target": ["name"]})
        cs.apply({"email": ["j@example.com"], "_target": ["email"]})
        assert cs.valid is True

    def test_apply_captures_validation_errors(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["J"], "_target": ["name"]})  # Too short
        assert cs.valid is False
        assert "name" in cs.errors

    def test_apply_only_shows_errors_for_touched_fields(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["John"], "_target": ["name"]})
        # email is missing but we only touched name
        # Error should only be for name if it has issues, not email
        # Actually in this case name is valid, so no errors for it
        # email error should not appear since it wasn't touched
        assert "email" not in cs.errors

    def test_apply_returns_self_for_chaining(self):
        cs = change_set(SimpleUser)
        result = cs.apply({"name": ["John"], "_target": ["name"]})
        assert result is cs

    def test_apply_model_validator_error(self):
        cs = change_set(UserWithPasswordConfirm)
        cs.apply({"username": ["john"], "_target": ["username"]})
        cs.apply({"password": ["secret"], "_target": ["password"]})
        cs.apply({"password_confirm": ["different"], "_target": ["password_confirm"]})
        assert cs.valid is False
        # Model-level error should be assigned to the last changed field
        assert "password_confirm" in cs.errors


class TestChangeSetSave:
    """Test save() method for form submission."""

    def test_save_valid_data(self):
        cs = change_set(SimpleUser)
        model = cs.save({"name": ["John"], "email": ["j@example.com"]})
        assert model is not None
        assert model.name == "John"
        assert cs.action == "submit"

    def test_save_invalid_data(self):
        cs = change_set(SimpleUser)
        model = cs.save({"name": ["J"], "email": ["j@example.com"]})
        assert model is None
        assert "name" in cs.errors

    def test_save_merges_into_changes(self):
        cs = change_set(SimpleUser, {"name": "John"})
        cs.save({"email": ["j@example.com"]})
        assert cs.changes["name"] == "John"
        assert cs.changes["email"] == "j@example.com"


class TestChangeSetNested:
    """Test nested model support."""

    def test_apply_nested_field(self):
        cs = change_set(UserWithAddress)
        cs.apply({"address.city": ["NYC"], "_target": ["address", "city"]})
        assert cs["address.city"] == "NYC"

    def test_apply_creates_nested_structure(self):
        cs = change_set(UserWithAddress)
        cs.apply({"address.city": ["NYC"], "_target": ["address", "city"]})
        assert cs.changes == {"address": {"city": "NYC"}}

    def test_apply_nested_validation_error(self):
        cs = change_set(UserWithAddress)
        cs.apply({"address.city": ["X"], "_target": ["address", "city"]})  # Too short
        assert cs.valid is False
        assert "address.city" in cs.errors

    def test_getitem_nested_path(self):
        cs = change_set(
            UserWithAddress,
            {"name": "John", "address": {"street": "123 Main", "city": "NYC"}},
        )
        assert cs["address.city"] == "NYC"
        assert cs["address.street"] == "123 Main"

    def test_getitem_missing_nested_returns_empty(self):
        cs = change_set(UserWithAddress)
        assert cs["address.city"] == ""


class TestChangeSetListFields:
    """Test list field support."""

    def test_apply_list_index(self):
        cs = change_set(UserWithTags)
        cs.apply({"tags.0": ["python"], "_target": ["tags", "0"]})
        assert cs["tags.0"] == "python"

    def test_apply_creates_list_structure(self):
        cs = change_set(UserWithTags)
        cs.apply({"tags.0": ["python"], "_target": ["tags", "0"]})
        assert cs.changes == {"tags": ["python"]}

    def test_apply_multiple_list_items(self):
        cs = change_set(UserWithTags)
        cs.apply({"tags.0": ["python"], "_target": ["tags", "0"]})
        cs.apply({"tags.1": ["web"], "_target": ["tags", "1"]})
        assert cs.changes["tags"] == ["python", "web"]


class TestChangeSetNestedList:
    """Test nested models in lists."""

    def test_apply_nested_list_field(self):
        cs = change_set(UserWithAddresses)
        cs.apply(
            {"addresses.0.city": ["NYC"], "_target": ["addresses", "0", "city"]}
        )
        assert cs["addresses.0.city"] == "NYC"

    def test_apply_creates_nested_list_structure(self):
        cs = change_set(UserWithAddresses)
        cs.apply(
            {"addresses.0.city": ["NYC"], "_target": ["addresses", "0", "city"]}
        )
        assert cs.changes == {"addresses": [{"city": "NYC"}]}

    def test_apply_nested_list_validation_error(self):
        cs = change_set(UserWithAddresses)
        cs.apply(
            {"addresses.0.city": ["X"], "_target": ["addresses", "0", "city"]}
        )  # Too short
        assert cs.valid is False
        assert "addresses.0.city" in cs.errors


class TestChangeSetGetFieldInfo:
    """Test get_field_info() method."""

    def test_simple_field(self):
        cs = change_set(SimpleUser)
        info = cs.get_field_info("name")
        assert info is not None
        assert info.annotation is str

    def test_nested_field(self):
        cs = change_set(UserWithAddress)
        info = cs.get_field_info("address.city")
        assert info is not None
        assert info.annotation is str

    def test_missing_field(self):
        cs = change_set(SimpleUser)
        info = cs.get_field_info("nonexistent")
        assert info is None

    def test_list_item_field(self):
        cs = change_set(UserWithAddresses)
        info = cs.get_field_info("addresses.0.city")
        assert info is not None
        assert info.annotation is str


class TestBackwardCompatibility:
    """Ensure existing usage patterns still work."""

    def test_flat_apply_still_works(self):
        # This is the pattern used in the plants example
        cs = change_set(SimpleUser)
        payload = {"name": ["John"], "_target": ["name"]}
        cs.apply(payload)
        assert cs["name"] == "John"

    def test_attrs_still_works_for_flat(self):
        cs = change_set(SimpleUser, {"name": "John", "email": "j@example.com"})
        assert cs.attrs.name == "John"

    def test_errors_dict_access(self):
        cs = change_set(SimpleUser)
        cs.apply({"name": ["J"], "_target": ["name"]})
        # Templates use errors.get("field")
        assert cs.errors.get("name") is not None
        assert cs.errors.get("email") is None
