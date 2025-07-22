"""
Polyfill for Python 3.14 t-strings (PEP 750).
This provides a mock implementation of Template strings for development.
When Python 3.14 is available, this can be replaced with native t-strings.
"""
from typing import Any, Tuple, Iterator, Union
from dataclasses import dataclass
import re


@dataclass
class Interpolation:
    """Represents an interpolation in a template."""
    value: Any
    conversion: Union[str, None] = None  # 'r', 's', 'a' or None
    format_spec: str = ""


class Template:
    """
    Mock implementation of Python 3.14 Template strings.
    
    This mimics the API described in PEP 750 for testing purposes.
    """
    
    def __init__(self, strings: Tuple[str, ...], interpolations: Tuple[Any, ...]):
        self._strings = strings
        self._interpolations = interpolations
        
        # Validate structure
        if len(strings) != len(interpolations) + 1:
            raise ValueError(
                f"Template must have exactly one more string than interpolations. "
                f"Got {len(strings)} strings and {len(interpolations)} interpolations."
            )
    
    @property
    def strings(self) -> Tuple[str, ...]:
        """The static string parts of the template."""
        return self._strings
    
    @property
    def interpolations(self) -> Tuple[Any, ...]:
        """The interpolated values."""
        return self._interpolations
    
    def __iter__(self) -> Iterator[Tuple[str, Union[Any, None]]]:
        """Iterate over (static, interpolation) pairs."""
        for i, static in enumerate(self._strings):
            if i < len(self._interpolations):
                yield (static, self._interpolations[i])
            else:
                yield (static, None)
    
    def __repr__(self) -> str:
        return f"Template(strings={self._strings!r}, interpolations={self._interpolations!r})"


def t(template_str: str, **kwargs) -> Template:
    """
    Create a Template from a template string.
    
    This is a development helper that parses a string with {var} placeholders.
    In real Python 3.14, this would be: t'Hello {name}!'
    
    Usage:
        template = t('<div>{content}</div>', content="Hello")
    """
    # Simple regex to find {var} patterns
    pattern = r'\{([^}]+)\}'
    parts = re.split(pattern, template_str)
    
    strings = []
    interpolations = []
    
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Even indices are static strings
            strings.append(part)
        else:
            # Odd indices are variable names
            if part in kwargs:
                interpolations.append(kwargs[part])
            else:
                # If not in kwargs, treat as a literal expression
                interpolations.append(f"{{{part}}}")
    
    # Ensure we have one more string than interpolations
    if len(strings) == len(interpolations):
        strings.append("")
    
    return Template(tuple(strings), tuple(interpolations))


# Example usage for testing
if __name__ == "__main__":
    # In Python 3.14, this would be: t'<div>{content}</div>'
    template = t('<div>{content}</div>', content="Hello, World!")
    
    print("Strings:", template.strings)  # ('<div>', '</div>')
    print("Interpolations:", template.interpolations)  # ('Hello, World!',)
    
    for static, interp in template:
        print(f"Static: {static!r}, Interpolation: {interp!r}")