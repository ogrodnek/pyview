"""
Tests for LiveViewTemplate processor.

NOTE: This test file uses t-string literal syntax and can only be run on Python 3.14+.
The pytest.skip call below prevents import errors on earlier Python versions.
"""
import sys
import pytest

# Skip entire module if Python < 3.14 (t-string literals cause SyntaxError)
if sys.version_info < (3, 14):
    pytest.skip("T-string tests require Python 3.14+", allow_module_level=True)

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

        # Plain string lists use empty statics wrapper, each string wrapped once
        expected = {
            "s": ["Fruits: ", ""],
            "0": {
                "s": ["", ""],
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
            "0": 1  # CID as number - Phoenix.js looks up in components[1]
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
        """Test list containing Template objects with different statics."""
        items = [
            t"Item 1",
            t"Item 2",
            t"Item 3"
        ]
        template = t"List: {items}"
        result = LiveViewTemplate.process(template)

        # Different templates have different statics, so use empty statics wrapper
        expected = {
            "s": ["List: ", ""],
            "0": {
                "s": ["", ""],
                "d": [
                    [{"s": ["Item 1"]}],
                    [{"s": ["Item 2"]}],
                    [{"s": ["Item 3"]}]
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

        # Mixed lists use empty statics wrapper, each item wrapped once
        expected = {
            "s": ["Mixed: ", ""],
            "0": {
                "s": ["", ""],
                "d": [
                    ["Plain string"],
                    [{"s": ["Template with ", ""], "0": "Alice"}],
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

        # Mixed list with different templates and dict - uses empty statics wrapper
        expected = {
            "s": ["Messages: ", ""],
            "0": {
                "s": ["", ""],
                "d": [
                    [{"s": ["Welcome ", ""], "0": "Alice"}],
                    [LiveViewTemplate.escape_html(str({"type": "dict", "value": 123}))],
                    [{"s": ["Goodbye ", ""], "0": "Alice"}]
                ]
            }
        }
        assert result == expected

    def test_list_comprehension_with_shared_statics(self):
        """Test list comprehension extracts shared statics for Phoenix.js wire format."""
        items = [
            t"<li>{i}</li>"
            for i in range(3)
        ]
        template = t"<ul>{items}</ul>"
        result = LiveViewTemplate.process(template)

        # Phoenix.js expects shared statics at top level and only dynamics in "d"
        expected = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "s": ["<li>", "</li>"],  # Shared statics from all list items
                "d": [
                    ["0"],  # Just the dynamic value for first item
                    ["1"],  # Just the dynamic value for second item
                    ["2"],  # Just the dynamic value for third item
                ]
            }
        }
        assert result == expected

    def test_list_comprehension_with_multiple_dynamics(self):
        """Test list comprehension with multiple dynamics per item."""
        items = [
            t"<li id=\"item-{i}\">{i * 2}</li>"
            for i in range(2)
        ]
        template = t"<ul>{items}</ul>"
        result = LiveViewTemplate.process(template)

        # Each item has two dynamics, statics are shared
        expected = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "s": ["<li id=\"item-", "\">", "</li>"],  # Shared statics
                "d": [
                    ["0", "0"],  # First item: id=0, content=0
                    ["1", "2"],  # Second item: id=1, content=2
                ]
            }
        }
        assert result == expected

    def test_list_of_component_placeholders(self):
        """Test list of LiveComponentPlaceholder objects."""
        socket = MockSocket()
        components = [
            LiveComponentPlaceholder(MockComponent, f"comp-{i}", {"index": i})
            for i in range(3)
        ]
        template = t"<div>{components}</div>"
        result = LiveViewTemplate.process(template, socket=socket)

        # Component CIDs are numbers, wrapped once in arrays for comprehension format
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [
                    [1],  # First component cid=1
                    [2],  # Second component cid=2
                    [3],  # Third component cid=3
                ]
            }
        }
        assert result == expected

        # Verify all components were registered
        assert len(socket.components._components) == 3
        assert socket.components._components[1]["id"] == "comp-0"
        assert socket.components._components[2]["id"] == "comp-1"
        assert socket.components._components[3]["id"] == "comp-2"

    def test_list_of_component_placeholders_without_socket(self):
        """Test list of LiveComponentPlaceholder objects without socket falls back to string."""
        components = [
            LiveComponentPlaceholder(MockComponent, f"comp-{i}", {"index": i})
            for i in range(2)
        ]
        template = t"<div>{components}</div>"
        result = LiveViewTemplate.process(template)  # No socket

        # Without socket, components become escaped strings wrapped once
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [
                    ["&lt;pyview-component cid=&#x27;comp-0&#x27;/&gt;"],
                    ["&lt;pyview-component cid=&#x27;comp-1&#x27;/&gt;"],
                ]
            }
        }
        assert result == expected

    def test_single_item_template_list(self):
        """Test list with single template item."""
        value = "test"
        items = [t"<span>{value}</span>"]
        template = t"<div>{items}</div>"
        result = LiveViewTemplate.process(template)

        # Single item list should still extract statics (all 1 items share same statics)
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["<span>", "</span>"],
                "d": [["test"]]
            }
        }
        assert result == expected

    def test_single_item_component_list(self):
        """Test list with single component."""
        socket = MockSocket()
        components = [LiveComponentPlaceholder(MockComponent, "solo", {"x": 1})]
        template = t"<div>{components}</div>"
        result = LiveViewTemplate.process(template, socket=socket)

        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [[1]]  # CID as number
            }
        }
        assert result == expected

    def test_mixed_list_template_then_component(self):
        """Test mixed list starting with template, containing component."""
        socket = MockSocket()
        comp = LiveComponentPlaceholder(MockComponent, "mix-1", {})
        name = "Alice"
        items = [
            t"<p>Hello {name}</p>",
            comp,
        ]
        template = t"<div>{items}</div>"
        result = LiveViewTemplate.process(template, socket=socket)

        # Mixed items use empty statics wrapper, each item wrapped
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [
                    [{"s": ["<p>Hello ", "</p>"], "0": "Alice"}],
                    [1],  # CID as number
                ]
            }
        }
        assert result == expected

    def test_mixed_list_component_then_template(self):
        """Test mixed list starting with component, containing template."""
        socket = MockSocket()
        comp = LiveComponentPlaceholder(MockComponent, "mix-2", {})
        name = "Bob"
        items = [
            comp,
            t"<p>Goodbye {name}</p>",
        ]
        template = t"<div>{items}</div>"
        result = LiveViewTemplate.process(template, socket=socket)

        # Mixed items use empty statics wrapper, each item wrapped
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [
                    [1],  # CID as number
                    [{"s": ["<p>Goodbye ", "</p>"], "0": "Bob"}],
                ]
            }
        }
        assert result == expected

    def test_template_comprehension_containing_component(self):
        """Test comprehension where each template contains a component."""
        socket = MockSocket()

        def make_item(i):
            comp = LiveComponentPlaceholder(MockComponent, f"inner-{i}", {"i": i})
            return t"<li>{comp}</li>"

        items = [make_item(i) for i in range(2)]
        template = t"<ul>{items}</ul>"
        result = LiveViewTemplate.process(template, socket=socket)

        # All templates share same statics, with component CIDs as dynamics
        expected = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "s": ["<li>", "</li>"],
                "d": [
                    [1],  # First template's dynamic is component cid=1
                    [2],  # Second template's dynamic is component cid=2
                ]
            }
        }
        assert result == expected

    def test_mixed_list_template_then_string(self):
        """Test mixed list with template then plain string."""
        name = "Test"
        items = [
            t"<p>Hello {name}</p>",
            "plain string",
        ]
        template = t"<div>{items}</div>"
        result = LiveViewTemplate.process(template)

        # Mixed items use empty statics wrapper, each item wrapped once
        expected = {
            "s": ["<div>", "</div>"],
            "0": {
                "s": ["", ""],
                "d": [
                    [{"s": ["<p>Hello ", "</p>"], "0": "Test"}],
                    ["plain string"],
                ]
            }
        }
        assert result == expected

    def test_list_comprehension_with_many_dynamics(self):
        """Test list comprehension with 10+ dynamics to verify ordering.

        This test ensures that dynamic values are extracted in the correct
        order (0, 1, 2, ..., 10, 11) rather than lexicographic order
        (0, 1, 10, 11, 2, ...) which would happen with string sorting.
        """
        # Create templates with 12 separate interpolations each
        # Each {f"..."} is a distinct interpolation
        items = [
            t"<tr><td>{f'{i}-0'}</td><td>{f'{i}-1'}</td><td>{f'{i}-2'}</td><td>{f'{i}-3'}</td><td>{f'{i}-4'}</td><td>{f'{i}-5'}</td><td>{f'{i}-6'}</td><td>{f'{i}-7'}</td><td>{f'{i}-8'}</td><td>{f'{i}-9'}</td><td>{f'{i}-10'}</td><td>{f'{i}-11'}</td></tr>"
            for i in range(2)
        ]
        template = t"<table>{items}</table>"
        result = LiveViewTemplate.process(template)

        # Verify the dynamics are in numeric order, not lexicographic
        # If sorted() was used with string keys, "10" and "11" would come after "1" but before "2"
        expected_dynamics_row_0 = ["0-0", "0-1", "0-2", "0-3", "0-4", "0-5", "0-6", "0-7", "0-8", "0-9", "0-10", "0-11"]
        expected_dynamics_row_1 = ["1-0", "1-1", "1-2", "1-3", "1-4", "1-5", "1-6", "1-7", "1-8", "1-9", "1-10", "1-11"]

        assert result["0"]["d"][0] == expected_dynamics_row_0
        assert result["0"]["d"][1] == expected_dynamics_row_1

