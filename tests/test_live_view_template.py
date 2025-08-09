"""
Tests for LiveViewTemplate processor.
"""
from pyview.template.live_view_template import LiveViewTemplate, LiveComponentPlaceholder


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
        template = t"Hello, World!"
        result = LiveViewTemplate.process(template)
        
        expected = {"s": ["Hello, World!"]}
        assert result == expected
    
    def test_string_interpolation(self):
        """Test string interpolation with HTML escaping."""
        name = "<script>alert('xss')</script>"
        template = t"Hello, {name}!"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Hello, ", "!"],
            "0": "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        }
        assert result == expected
    
    def test_multiple_interpolations(self):
        """Test multiple interpolations in one template."""
        greeting = "Hello"
        name = "Alice"
        count = 5
        template = t"{greeting}, {name}! You have {count} messages."
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
        s = "hello"
        i = 42
        f = 3.14
        b = True
        template = t"String: {s}, Int: {i}, Float: {f}, Bool: {b}"
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
        template = t"Fruits: {items}"
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
        items = []
        template = t"Items: {items}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Items: ", ""],
            "0": ""
        }
        assert result == expected
    
    def test_nested_template(self):
        """Test nested template processing."""
        content = "Hello"
        inner_template = t"<span>{content}</span>"
        outer_template = t"<div>{inner_template}</div>"
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
        comp = LiveComponentPlaceholder(MockComponent, "test-1", {"foo": "bar"})
        template = t"<div>{comp}</div>"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["<div>", "</div>"],
            "0": "<pyview-component cid='test-1'/>"
        }
        assert result == expected
    
    def test_live_component_with_socket(self):
        """Test live component with socket."""
        socket = MockSocket()
        comp = LiveComponentPlaceholder(MockComponent, "test-1", {"foo": "bar"})
        template = t"<div>{comp}</div>"
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
        
        content = SafeHTML("<strong>Bold</strong>")
        template = t"<div>{content}</div>"
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
    
    def test_none_interpolation(self):
        """Test None value interpolation."""
        value = None
        template = t"Value: {value}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Value: ", ""],
            "0": "None"  # None is converted to string
        }
        assert result == expected
    
    def test_dict_interpolation(self):
        """Test dictionary interpolation."""
        data = {"key": "value", "num": 42}
        template = t"Data: {data}"
        result = LiveViewTemplate.process(template)
        
        # Dicts should be converted to escaped string representation
        expected = {
            "s": ["Data: ", ""],
            "0": LiveViewTemplate.escape_html(str(data))
        }
        assert result == expected
    
    def test_custom_object_interpolation(self):
        """Test custom object without __html__ method."""
        class CustomObject:
            def __str__(self):
                return "<custom>"
        
        obj = CustomObject()
        template = t"Object: {obj}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Object: ", ""],
            "0": "&lt;custom&gt;"  # Should be HTML escaped
        }
        assert result == expected
    
    def test_template_only_interpolation(self):
        """Test template with only an interpolation."""
        value = "test"
        template = t"{value}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["", ""],
            "0": "test"
        }
        assert result == expected
    
    def test_expression_interpolation(self):
        """Test expressions in interpolations."""
        x = 5
        y = 3
        items = ["a", "b", "c"]
        obj = type('obj', (), {'attr': 'value'})()
        
        template = t"Sum: {x + y}, Length: {len(items)}, Attr: {obj.attr}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Sum: ", ", Length: ", ", Attr: ", ""],
            "0": "8",
            "1": "3",
            "2": "value"
        }
        assert result == expected
    
    def test_unicode_characters(self):
        """Test Unicode characters in templates."""
        emoji = "🎉"
        chinese = "你好"
        template = t"Unicode: {emoji} {chinese}!"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Unicode: ", " ", "!"],
            "0": "🎉",
            "1": "你好"
        }
        assert result == expected
    
    def test_list_of_templates(self):
        """Test list containing Template objects."""
        items = [
            t"Item 1",
            t"Item 2", 
            t"Item 3"
        ]
        template = t"List: {items}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["List: ", ""],
            "0": {
                "d": [
                    {"s": ["Item 1"]},
                    {"s": ["Item 2"]},
                    {"s": ["Item 3"]}
                ]
            }
        }
        assert result == expected
    
    def test_mixed_list_with_templates(self):
        """Test list with mixed Template and string items."""
        name = "Alice"
        items = [
            "Plain string",
            t"Template with {name}",
            42
        ]
        template = t"Mixed: {items}"
        result = LiveViewTemplate.process(template)
        
        # Mixed lists should process templates and escape strings
        expected = {
            "s": ["Mixed: ", ""],
            "0": {
                "d": [
                    ["Plain string"],
                    {"s": ["Template with ", ""], "0": "Alice"},
                    ["42"]
                ]
            }
        }
        assert result == expected
    
    def test_empty_interpolation(self):
        """Test empty string interpolation."""
        empty = ""
        template = t"Empty: [{empty}]"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Empty: [", "]"],
            "0": ""
        }
        assert result == expected
    
    def test_whitespace_preservation(self):
        """Test that whitespace is preserved correctly."""
        value = "test"
        template = t"  {value}  \n  {value}  "
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["  ", "  \n  ", "  "],
            "0": "test",
            "1": "test"
        }
        assert result == expected
    
    def test_escaped_braces(self):
        """Test that escaped braces work correctly."""
        # In Python 3.14 t-strings, {{ becomes a literal {
        template = t"Literal braces: {{ and }}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Literal braces: { and }"]
        }
        assert result == expected
    
    def test_format_specifier(self):
        """Test format specifiers in t-strings."""
        value = 3.14159
        template = t"Pi: {value:.2f}"
        result = LiveViewTemplate.process(template)
        
        # The interpolation object contains the format spec
        # We need to check what the actual output is
        expected = {
            "s": ["Pi: ", ""],
            "0": "3.14"  # Should be formatted
        }
        assert result == expected
    
    def test_callable_result(self):
        """Test interpolating the result of a function call."""
        def get_greeting():
            return "<Hello>"
        
        template = t"Message: {get_greeting()}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Message: ", ""],
            "0": "&lt;Hello&gt;"  # Should be escaped
        }
        assert result == expected
    
    def test_complex_nested_structure(self):
        """Test complex nested structure with multiple template types."""
        user = "Alice"
        items = [
            t"Welcome {user}",
            {"type": "dict", "value": 123},
            t"Goodbye {user}"
        ]
        
        template = t"Messages: {items}"
        result = LiveViewTemplate.process(template)
        
        expected = {
            "s": ["Messages: ", ""],
            "0": {
                "d": [
                    {"s": ["Welcome ", ""], "0": "Alice"},
                    [LiveViewTemplate.escape_html(str({"type": "dict", "value": 123}))],
                    {"s": ["Goodbye ", ""], "0": "Alice"}
                ]
            }
        }
        assert result == expected
    