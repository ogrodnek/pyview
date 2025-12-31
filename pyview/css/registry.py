"""
CSS Registry - tracks and serves content-hashed CSS files.

CSS files are discovered next to view/component Python files and served
with content-based hashes for optimal caching.

Example:
    views/kanban/kanban.py  -> views/kanban/kanban.css
    URL: /pyview-css/views.kanban.Kanban.a1b2c3d4.css
"""

import hashlib
import inspect
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CSSEntry:
    """A registered CSS file with content hash for cache busting."""

    name: str
    file_path: str
    content: str
    hash: str

    @classmethod
    def from_file(cls, name: str, file_path: str) -> "CSSEntry":
        """Create a CSSEntry by reading and hashing a CSS file."""
        content = Path(file_path).read_text()
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return cls(name=name, file_path=file_path, content=content, hash=content_hash)

    @property
    def url(self) -> str:
        """URL path for this CSS file."""
        return f"/pyview-css/{self.name}.{self.hash}.css"

    @property
    def link_tag(self) -> str:
        """HTML link tag for this CSS file."""
        return f'<link rel="stylesheet" href="{self.url}">'

    def refresh_if_changed(self) -> bool:
        """
        Check if file has changed and refresh content/hash if so.

        Returns True if the file was refreshed.
        """
        try:
            current_content = Path(self.file_path).read_text()
            current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:8]

            if current_hash != self.hash:
                self.content = current_content
                self.hash = current_hash
                return True
            return False
        except OSError:
            return False


class CSSRegistry:
    """
    Registry for CSS files associated with views and components.

    Tracks CSS files by name (module.ClassName) and content hash.
    Provides lookup for serving and link tag generation.
    """

    def __init__(self, auto_refresh: bool = False):
        """
        Initialize the CSS registry.

        Args:
            auto_refresh: If True, check for file changes on each request.
                         Useful for development, disable in production.
        """
        self._entries: dict[str, CSSEntry] = {}  # name -> entry
        self._by_url_key: dict[str, CSSEntry] = {}  # "name.hash" -> entry
        self.auto_refresh = auto_refresh

    def register(self, name: str, file_path: str) -> CSSEntry:
        """
        Register a CSS file.

        Args:
            name: Unique name (typically module.ClassName)
            file_path: Absolute path to the CSS file

        Returns:
            The registered CSSEntry
        """
        entry = CSSEntry.from_file(name, file_path)
        self._entries[name] = entry
        self._by_url_key[f"{name}.{entry.hash}"] = entry
        logger.debug(f"Registered CSS: {name} -> {entry.url}")
        return entry

    def register_for_class(self, cls: type) -> Optional[CSSEntry]:
        """
        Register CSS for a class if a colocated .css file exists.

        Looks for a .css file next to the class's .py file.

        Args:
            cls: The class (LiveView or LiveComponent subclass)

        Returns:
            CSSEntry if CSS file found, None otherwise
        """
        css_path = self._find_css_for_class(cls)
        if css_path:
            name = f"{cls.__module__}.{cls.__name__}"
            # Check if already registered
            if name in self._entries:
                return self._entries[name]
            return self.register(name, css_path)
        return None

    def get(self, name: str) -> Optional[CSSEntry]:
        """Get a CSS entry by name."""
        entry = self._entries.get(name)
        if entry and self.auto_refresh and entry.refresh_if_changed():
            # Update URL key mapping
            old_keys = [k for k, v in self._by_url_key.items() if v.name == name]
            for k in old_keys:
                del self._by_url_key[k]
            self._by_url_key[f"{name}.{entry.hash}"] = entry
            logger.debug(f"Refreshed CSS: {name} -> {entry.url}")
        return entry

    def get_for_class(self, cls: type) -> Optional[CSSEntry]:
        """Get CSS entry for a class."""
        name = f"{cls.__module__}.{cls.__name__}"
        return self.get(name)

    def get_for_serving(self, name_with_hash: str) -> Optional[CSSEntry]:
        """
        Get a CSS entry for serving by URL key (name.hash).

        Args:
            name_with_hash: The "name.hash" portion of the URL

        Returns:
            CSSEntry if found and hash matches, None otherwise
        """
        return self._by_url_key.get(name_with_hash)

    def has(self, name: str) -> bool:
        """Check if a CSS entry is registered."""
        return name in self._entries

    def _find_css_for_class(self, cls: type) -> Optional[str]:
        """Find a colocated CSS file for a class."""
        try:
            py_file = inspect.getfile(cls)
            if py_file.endswith(".py"):
                css_file = py_file[:-3] + ".css"
                if os.path.isfile(css_file):
                    return css_file
        except (TypeError, OSError):
            pass
        return None

    def clear(self) -> None:
        """Clear all registered entries."""
        self._entries.clear()
        self._by_url_key.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries
