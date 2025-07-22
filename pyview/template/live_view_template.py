"""
LiveViewTemplate processor for Python t-strings.
Converts Template objects into LiveView's diff tree structure.
"""
from typing import Any, Union
from dataclasses import dataclass

# Import our polyfill (in Python 3.14, this would be: from types import Template)
from .tstring_polyfill import Template


@dataclass
class LiveComponentPlaceholder:
    """Placeholder for live components in templates."""
    component_class: type
    component_id: str
    assigns: dict[str, Any]
    
    def __str__(self):
        # Return a placeholder that gets replaced during rendering
        return f"<pyview-component cid='{self.component_id}'/>"


class LiveViewTemplate:
    """Processes Python t-string Templates into LiveView diff tree format."""
    
    @staticmethod
    def process(template: Template, socket: Any = None) -> dict[str, Any]:
        """
        Convert a Python Template to LiveView diff tree format.
        
        The LiveView tree format:
        {
            "s": ["static", "parts", "here"],  # Static strings
            "0": "dynamic value",              # Dynamic values indexed by position
            "1": { "s": [...], "0": ... },    # Nested structures
            "d": [[...], [...]]               # For comprehensions (loops)
        }
        """
        parts: dict[str, Any] = {"s": []}
        
        # Process the template using iterator
        interp_index = 0
        for static, interp in template:
            parts["s"].append(static)
            
            # Check if there's an interpolation
            if interp is not None:
                key = str(interp_index)
                
                # Handle different interpolation types
                if isinstance(interp, LiveComponentPlaceholder):
                    # Handle live component
                    if socket and hasattr(socket, 'components'):
                        cid = socket.components.register(
                            interp.component_class,
                            interp.component_id,
                            interp.assigns
                        )
                        parts[key] = {"c": cid}
                    else:
                        # Fallback if no socket available
                        parts[key] = str(interp)
                
                elif isinstance(interp, Template):
                    # Handle nested templates
                    parts[key] = LiveViewTemplate.process(interp, socket)
                
                elif isinstance(interp, str):
                    # Simple string interpolation (HTML escaped)
                    parts[key] = LiveViewTemplate.escape_html(interp)
                
                elif isinstance(interp, (int, float, bool)):
                    # Primitive types
                    parts[key] = str(interp)
                
                elif isinstance(interp, list):
                    # Handle list comprehensions
                    parts[key] = LiveViewTemplate._process_list(interp, socket)
                
                elif hasattr(interp, '__html__'):
                    # Handle objects that can render as HTML (like Markup)
                    parts[key] = str(interp.__html__())
                
                else:
                    # Default: convert to string and escape
                    parts[key] = LiveViewTemplate.escape_html(str(interp))
                
                interp_index += 1
        
        return parts
    
    @staticmethod
    def _process_list(items: list, socket: Any = None) -> Union[dict[str, Any], str]:
        """Process a list of items for the 'd' (dynamics) format."""
        if not items:
            return ""
        
        # If all items are templates, process them
        if all(isinstance(item, Template) for item in items):
            return {
                "d": [LiveViewTemplate.process(item, socket) for item in items]
            }
        
        # Otherwise, convert to strings with HTML escaping
        return {
            "d": [[LiveViewTemplate.escape_html(str(item))] for item in items]
        }
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )


def live_component(
    component_class: type,
    id: str,
    **assigns
) -> LiveComponentPlaceholder:
    """
    Insert a live component into a template.
    
    Usage:
        from .tstring_polyfill import t
        template = t('<div>{comp}</div>', comp=live_component(MyComponent, id="comp-1", foo="bar"))
    """
    return LiveComponentPlaceholder(
        component_class=component_class,
        component_id=id,
        assigns=assigns
    )


# Convenience function for creating templates (development helper)
def html(template_str: str, **kwargs) -> dict[str, Any]:
    """
    Create and process a template in one step.
    
    Usage:
        tree = html('<div>{content}</div>', content="Hello")
    """
    from .tstring_polyfill import t
    template = t(template_str, **kwargs)
    return LiveViewTemplate.process(template)