"""No-operation implementation of instrumentation interfaces."""

from typing import Any, Optional
from .interfaces import (
    InstrumentationProvider,
    Counter,
    UpDownCounter,
    Gauge,
    Histogram,
    Span,
)


class NoOpCounter(Counter):
    """No-op counter implementation."""
    
    def add(self, value: float = 1, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op: does nothing."""
        pass


class NoOpUpDownCounter(UpDownCounter):
    """No-op up/down counter implementation."""
    
    def add(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op: does nothing."""
        pass


class NoOpGauge(Gauge):
    """No-op gauge implementation."""
    
    def set(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op: does nothing."""
        pass


class NoOpHistogram(Histogram):
    """No-op histogram implementation."""
    
    def record(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op: does nothing."""
        pass


class NoOpSpan(Span):
    """No-op span implementation."""
    
    def set_attribute(self, key: str, value: Any) -> None:
        """No-op: does nothing."""
        pass
    
    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """No-op: does nothing."""
        pass
    
    def end(self, status: str = "ok") -> None:
        """No-op: does nothing."""
        pass


class NoOpInstrumentation(InstrumentationProvider):
    """
    Default no-operation instrumentation provider.
    
    This implementation does nothing and has zero performance overhead.
    It's used as the default when no instrumentation is configured.
    """
    
    def __init__(self):
        """Initialize the no-op provider."""
        # Cache single instances to avoid object creation overhead
        self._counter = NoOpCounter()
        self._updown_counter = NoOpUpDownCounter()
        self._gauge = NoOpGauge()
        self._histogram = NoOpHistogram()
        self._span = NoOpSpan()
    
    def create_counter(self, name: str, description: str = "", unit: str = "") -> Counter:
        """Return a no-op counter."""
        return self._counter
    
    def create_updown_counter(self, name: str, description: str = "", unit: str = "") -> UpDownCounter:
        """Return a no-op up/down counter."""
        return self._updown_counter
    
    def create_gauge(self, name: str, description: str = "", unit: str = "") -> Gauge:
        """Return a no-op gauge."""
        return self._gauge
    
    def create_histogram(self, name: str, description: str = "", unit: str = "") -> Histogram:
        """Return a no-op histogram."""
        return self._histogram
    
    def start_span(self, name: str, attributes: Optional[dict[str, Any]] = None) -> Span:
        """Return a no-op span."""
        return self._span