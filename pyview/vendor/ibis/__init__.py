from . import compiler, errors, filters, loaders, nodes
from .template import Template

# Library version.
__version__ = "3.2.1"

__all__ = ["compiler", "errors", "filters", "loaders", "nodes", "Template"]


# Assign a template-loading callable here to enable the {% include %} and {% extends %} tags.
# The callable should accept a single string argument and either return an instance of the
# corresponding Template class or raise a TemplateLoadError exception.
loader = None
