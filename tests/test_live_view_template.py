"""
Tests for LiveViewTemplate processor.
"""
import pytest
from pyview.template.live_view_template import LiveViewTemplate, LiveComponentPlaceholder, html
from pyview.template.tstring_polyfill import Template, t


class MockComponent:
    """Mock component class for testing."""
    pass


class MockSocket:
    """Mock socket for testing component integration."""
    
    def __init__(self):
        self.components = MockComponentsManager()


class MockComponentsManager:
    """Mock components manager for testing."""
    
    def __init__(self):
        self._components = {}
        self._next_cid = 1
    
    def register(self, component_class, component_id, assigns):
        cid = self._next_cid
        self._next_cid += 1
        self._components[cid] = {
            "class": component_class,
            "id": component_id,
            "assigns": assigns
        }
        return cid


class TestLiveViewTemplate:
    """Test LiveViewTemplate processor."""
    
    def test_simple_template(self):
        """Test processing a simple template with no interpolations."""
        template = t("Hello, World!")
        result = LiveViewTemplate.process(template)
        
        expected = {"s": ["Hello, World!"]}
        assert result == expected
    
    def test_string_interpolation(self):
        """Test string interpolation with HTML escaping."""
        template = t("Hello, {name}!", name="<script>alert('xss')</script>")
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Hello, ", "!"],
            "0": "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        }
        assert result == expected
    
    def test_multiple_interpolations(self):
        """Test multiple interpolations in one template."""
        template = t("{greeting}, {name}! You have {count} messages.", 
                    greeting="Hello", name="Alice", count=5)
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["", ", ", "! You have ", " messages."],
            "0": "Hello",
            "1": "Alice", 
            "2": "5"
        }
        assert result == expected
    
    def test_primitive_types(self):
        """Test various primitive type interpolations."""
        template = t("String: {s}, Int: {i}, Float: {f}, Bool: {b}",
                    s="hello", i=42, f=3.14, b=True)
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["String: ", ", Int: ", ", Float: ", ", Bool: ", ""],
            "0": "hello",
            "1": "42",
            "2": "3.14", 
            "3": "True"
        }
        assert result == expected
    
    def test_list_interpolation(self):
        """Test list interpolation."""
        items = ["apple", "banana", "cherry"]
        template = t("Fruits: {items}", items=items)
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Fruits: ", ""],
            "0": {
                "d": [["apple"], ["banana"], ["cherry"]]
            }
        }
        assert result == expected
    
    def test_empty_list(self):
        """Test empty list interpolation."""
        template = t("Items: {items}", items=[])
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Items: ", ""],
            "0": ""
        }
        assert result == expected
    
    def test_nested_template(self):
        """Test nested template processing."""
        inner_template = t("<span>{content}</span>", content="Hello")
        outer_template = t("<div>{inner}</div>", inner=inner_template)
        result = LiveViewTemplate.process(outer_template)
        
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["<span>", "</span>"],
                "0": "Hello"
            }
        }
        assert result == expected
    
    def test_live_component_without_socket(self):
        """Test live component placeholder without socket."""
        component_placeholder = LiveComponentPlaceholder(MockComponent, "test-1", {"foo": "bar"})
        template = t("<div>{comp}</div>", comp=component_placeholder)
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["<div>", "</div>"],
            "0": "<pyview-component cid='test-1'/>"
        }
        assert result == expected
    
    def test_live_component_with_socket(self):
        """Test live component with socket."""
        socket = MockSocket()
        component_placeholder = LiveComponentPlaceholder(MockComponent, "test-1", {"foo": "bar"})
        template = t("<div>{comp}</div>", comp=component_placeholder)
        result = LiveViewTemplate.process(template, socket=socket)
        
        expected = {
            "s": ["<div>", "</div>"],
            "0": {"c": 1}  # First registered component gets cid=1
        }
        assert result == expected
        
        # Verify component was registered correctly
        assert socket.components._components[1] == {
            "class": MockComponent,
            "id": "test-1", 
            "assigns": {"foo": "bar"}
        }
    
    def test_html_markup_object(self):
        """Test objects with __html__ method."""
        class SafeHTML:
            def __init__(self, html):
                self.html = html
            def __html__(self):
                return self.html
        
        safe_content = SafeHTML("<strong>Bold</strong>")
        template = t("<div>{content}</div>", content=safe_content)
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["<div>", "</div>"],
            "0": "<strong>Bold</strong>"
        }
        assert result == expected
    
    def test_html_escaping(self):
        """Test HTML character escaping."""
        dangerous = '<script>alert("xss")</script>'
        result = LiveViewTemplate.escape_html(dangerous)
        expected = '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert result == expected
    
    def test_convenience_html_function(self):
        """Test the convenience html() function."""
        result = html("<div>{name}</div>", name="Alice")
        expected = {
            "s": ["<div>", "</div>"],
            "0": "Alice"
        }
        assert result == expected


class TestTemplate:
    """Test our Template polyfill."""
    
    def test_template_creation(self):
        """Test basic Template creation."""
        template = Template(("Hello, ", "!"), ("World",))
        assert template.strings == ("Hello, ", "!")
        assert template.interpolations == ("World",)
    
    def test_template_iteration(self):
        """Test Template iteration."""
        template = Template(("Hello, ", "!"), ("World",))
        pairs = list(template)
        expected = [("Hello, ", "World"), ("!", None)]
        assert pairs == expected
    
    def test_template_validation(self):
        """Test Template validation."""
        # Should work: n strings, n-1 interpolations
        Template(("a", "b", "c"), ("x", "y"))
        
        # Should fail: mismatched counts
        with pytest.raises(ValueError):
            Template(("a", "b"), ("x", "y"))  # Same count
        
        with pytest.raises(ValueError):
            Template(("a",), ("x", "y"))  # More interps than strings
    
    def test_t_function(self):
        """Test the t() helper function."""
        template = t("Hello, {name}!", name="World")
        assert template.strings == ("Hello, ", "!")
        assert template.interpolations == ("World",)
    
    def test_t_function_multiple_vars(self):
        """Test t() with multiple variables."""
        template = t("{greeting}, {name}!", greeting="Hi", name="Alice")
        assert template.strings == ("", ", ", "!")
        assert template.interpolations == ("Hi", "Alice")
    
    def test_t_function_no_vars(self):
        """Test t() with no variables."""
        template = t("Hello, World!")
        assert template.strings == ("Hello, World!",)
        assert template.interpolations == ()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])