import pytest
from starlette.routing import compile_path

from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView


class MockLiveView(LiveView):
    pass


class UserLiveView(LiveView):
    pass


class ProductLiveView(LiveView):
    pass


class BlogPostLiveView(LiveView):
    pass


@pytest.fixture
def routes_lookup():
    lookup = LiveViewLookup()
    # Add a mix of static and parameterized routes
    lookup.add("/", lambda: MockLiveView())
    lookup.add("/users", lambda: UserLiveView())
    lookup.add("/users/{user_id}", lambda: UserLiveView())
    lookup.add("/products/{product_id:int}", lambda: ProductLiveView())
    lookup.add("/blog/{year:int}/{month:int}/{slug}", lambda: BlogPostLiveView())
    return lookup


class TestLiveViewLookup:
    # Given a route with no parameters
    # When we look up an exact path match
    # Then we get the correct LiveView with empty params and no action
    def test_exact_path_match(self, routes_lookup):
        view, params, action = routes_lookup.get("/users")
        assert isinstance(view, UserLiveView)
        assert params == {}
        assert action is None

    # Given a route with trailing slash
    # When we look up the path
    # Then we get the correct LiveView by removing the trailing slash
    def test_trailing_slash(self, routes_lookup):
        view, params, action = routes_lookup.get("/users/")
        assert isinstance(view, UserLiveView)
        assert params == {}
        assert action is None

    # Given a route with path parameters
    # When we look up a matching path
    # Then we get the correct LiveView with extracted parameters
    def test_path_parameters(self, routes_lookup):
        view, params, action = routes_lookup.get("/users/123")
        assert isinstance(view, UserLiveView)
        assert params == {"user_id": "123"}
        assert action is None

    # Given a route with type-converted path parameters
    # When we look up a matching path
    # Then we get the correct LiveView with properly converted parameters
    def test_type_conversion(self, routes_lookup):
        view, params, action = routes_lookup.get("/products/456")
        assert isinstance(view, ProductLiveView)
        assert params == {"product_id": 456}
        assert isinstance(params["product_id"], int)
        assert action is None

    # Given a route with multiple parameters
    # When we look up a matching path
    # Then we get all parameters correctly extracted and converted
    def test_multiple_parameters(self, routes_lookup):
        view, params, action = routes_lookup.get("/blog/2023/05/hello-world")
        assert isinstance(view, BlogPostLiveView)
        assert params == {"year": 2023, "month": 5, "slug": "hello-world"}
        assert isinstance(params["year"], int)
        assert isinstance(params["month"], int)
        assert isinstance(params["slug"], str)
        assert action is None

    # Given a non-existent path
    # When we look it up
    # Then we get a ValueError
    def test_nonexistent_path(self, routes_lookup):
        with pytest.raises(ValueError) as excinfo:
            routes_lookup.get("/nonexistent")
        assert "No LiveView found for path" in str(excinfo.value)

    # Given an invalid type for a type-converted parameter
    # When we look up the path
    # Then it doesn't match and raises ValueError
    def test_invalid_type_conversion(self, routes_lookup):
        with pytest.raises(ValueError):
            routes_lookup.get("/products/not-an-integer")

    # Given a path that conflicts with a more specific path
    # When we look up the path
    # Then the most specific match wins
    def test_specific_path_priority(self):
        lookup = LiveViewLookup()
        lookup.add("/items/{id}", lambda: MockLiveView())
        lookup.add("/items/special", lambda: UserLiveView())

        # The specific path should match, not the parameter path
        view, params, action = lookup.get("/items/special")
        assert isinstance(view, UserLiveView)
        assert params == {}
        assert action is None

    # Given the starlette compile_path function
    # When we compile different path patterns
    # Then it correctly handles various parameter types
    def test_starlette_compile_path(self):
        # Test basic path compilation
        path_regex, _, _ = compile_path("/users/{user_id}")
        match = path_regex.match("/users/123")
        assert match is not None
        assert match.groupdict() == {"user_id": "123"}

        # Test with type conversion
        path_regex, _, _ = compile_path("/users/{user_id:int}")
        match = path_regex.match("/users/123")
        assert match is not None
        assert match.groupdict() == {"user_id": "123"}  # Still a string at this point


class TestRouteActions:
    """Tests for route action functionality."""

    # Given a route registered with an action
    # When we look up the path
    # Then we get the action back along with the LiveView and params
    def test_action_returned_from_get(self):
        lookup = LiveViewLookup()
        lookup.add("/articles", lambda: MockLiveView(), action="index")

        view, params, action = lookup.get("/articles")
        assert isinstance(view, MockLiveView)
        assert params == {}
        assert action == "index"

    # Given multiple routes with different actions to the same LiveView
    # When we look up each path
    # Then we get the correct action for each
    def test_multiple_actions_same_liveview(self):
        lookup = LiveViewLookup()
        lookup.add("/articles", lambda: MockLiveView(), action="index")
        lookup.add("/articles/new", lambda: MockLiveView(), action="new")
        lookup.add("/articles/{id:int}/edit", lambda: MockLiveView(), action="edit")

        # Check index action
        view, params, action = lookup.get("/articles")
        assert isinstance(view, MockLiveView)
        assert action == "index"
        assert params == {}

        # Check new action
        view, params, action = lookup.get("/articles/new")
        assert isinstance(view, MockLiveView)
        assert action == "new"
        assert params == {}

        # Check edit action with path param
        view, params, action = lookup.get("/articles/42/edit")
        assert isinstance(view, MockLiveView)
        assert action == "edit"
        assert params == {"id": 42}

    # Given routes without actions
    # When we look up the path
    # Then action is None (backward compatibility)
    def test_no_action_returns_none(self):
        lookup = LiveViewLookup()
        lookup.add("/legacy", lambda: MockLiveView())

        view, params, action = lookup.get("/legacy")
        assert isinstance(view, MockLiveView)
        assert action is None

    # Given routes with actions registered for the same LiveView class
    # When we check if a path belongs to an action group
    # Then is_same_action_group returns True for paths in the group
    def test_action_group_tracking(self):
        lookup = LiveViewLookup()
        lookup.add("/articles", MockLiveView, action="index")
        lookup.add("/articles/new", MockLiveView, action="new")
        lookup.add("/other", UserLiveView, action="show")

        # Paths in the same action group
        assert lookup.is_same_action_group(MockLiveView, "/articles")
        assert lookup.is_same_action_group(MockLiveView, "/articles/new")

        # Different class
        assert not lookup.is_same_action_group(MockLiveView, "/other")
        assert lookup.is_same_action_group(UserLiveView, "/other")

    # Given a route without an action
    # When we check if it's in an action group
    # Then is_same_action_group returns False
    def test_no_action_not_in_group(self):
        lookup = LiveViewLookup()
        lookup.add("/legacy", MockLiveView)  # No action

        assert not lookup.is_same_action_group(MockLiveView, "/legacy")

    # Given mixed routes (some with actions, some without) for the same class
    # When we look them up
    # Then each returns the correct action (or None)
    def test_mixed_action_and_no_action(self):
        lookup = LiveViewLookup()
        lookup.add("/articles", lambda: MockLiveView(), action="index")
        lookup.add("/articles/legacy", lambda: MockLiveView())  # No action

        view1, _, action1 = lookup.get("/articles")
        assert action1 == "index"

        view2, _, action2 = lookup.get("/articles/legacy")
        assert action2 is None
