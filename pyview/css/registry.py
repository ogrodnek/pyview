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
        content = Path(file_path).read_text()
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return cls(name=name, file_path=file_path, content=content, hash=content_hash)

    @property
    def url(self) -> str:
        return f"/pyview-css/{self.name}.{self.hash}.css"

    @property
    def link_tag(self) -> str:
        return f'<link rel="stylesheet" href="{self.url}">'

    def refresh_if_changed(self) -> bool:
        """Check if file has changed and refresh content/hash if so."""
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
        self._entries: dict[str, CSSEntry] = {}
        self._by_url_key: dict[str, CSSEntry] = {}
        self.auto_refresh = auto_refresh

    def register(self, name: str, file_path: str) -> CSSEntry:
        entry = CSSEntry.from_file(name, file_path)
        self._entries[name] = entry
        self._by_url_key[f"{name}.{entry.hash}"] = entry
        logger.debug(f"Registered CSS: {name} -> {entry.url}")
        return entry

    def register_for_class(self, cls: type) -> Optional[CSSEntry]:
        """Register CSS for a class if a colocated .css file exists."""
        name = f"{cls.__module__}.{cls.__name__}"
        if name in self._entries:
            entry = self._entries[name]
            if self.auto_refresh and entry.refresh_if_changed():
                self._reindex(name, entry)
            return entry

        css_path = _find_css_for_class(cls)
        if css_path:
            return self.register(name, css_path)
        return None

    def get_for_serving(self, name_with_hash: str) -> Optional[CSSEntry]:
        """Get a CSS entry for serving by URL key (name.hash)."""
        return self._by_url_key.get(name_with_hash)

    def _reindex(self, name: str, entry: CSSEntry) -> None:
        """Update URL key mapping after a hash change."""
        old_keys = [k for k, v in self._by_url_key.items() if v.name == name]
        for k in old_keys:
            del self._by_url_key[k]
        self._by_url_key[f"{name}.{entry.hash}"] = entry
        logger.debug(f"Refreshed CSS: {name} -> {entry.url}")

    def clear(self) -> None:
        self._entries.clear()
        self._by_url_key.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries


def _find_css_for_class(cls: type) -> Optional[str]:
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
