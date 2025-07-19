"""Abstract base classes for PyView instrumentation."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Callable, Union
from contextlib import contextmanager
import functools
import time
import asyncio


class Counter(ABC):
    """A monotonically increasing counter metric."""
    
    @abstractmethod
    def add(self, value: float = 1, attributes: Optional[dict[str, Any]] = None) -> None:
        """Add to the counter value."""
        pass


class UpDownCounter(ABC):
    """A counter that can increase or decrease."""
    
    @abstractmethod
    def add(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Add to the counter value (can be negative)."""
        pass


class Gauge(ABC):
    """A point-in-time value metric."""
    
    @abstractmethod
    def set(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Set the gauge to a specific value."""
        pass


class Histogram(ABC):
    """A metric that tracks the distribution of values."""
    
    @abstractmethod
    def record(self, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Record a value in the histogram."""
        pass


class Span(ABC):
    """A span representing a unit of work."""
    
    @abstractmethod
    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        pass
    
    @abstractmethod
    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        pass
    
    @abstractmethod
    def end(self, status: str = "ok") -> None:
        """End the span with a status."""
        pass


class InstrumentationProvider(ABC):
    """Abstract base class for instrumentation providers."""
    
    # Create instruments (efficient, reusable)
    @abstractmethod
    def create_counter(self, name: str, description: str = "", unit: str = "") -> Counter:
        """Create a counter instrument."""
        pass
    
    @abstractmethod
    def create_updown_counter(self, name: str, description: str = "", unit: str = "") -> UpDownCounter:
        """Create an up/down counter instrument."""
        pass
    
    @abstractmethod
    def create_gauge(self, name: str, description: str = "", unit: str = "") -> Gauge:
        """Create a gauge instrument."""
        pass
    
    @abstractmethod
    def create_histogram(self, name: str, description: str = "", unit: str = "") -> Histogram:
        """Create a histogram instrument."""
        pass
    
    # Convenience methods (simple, pass name each time)
    def increment_counter(self, name: str, value: float = 1, attributes: Optional[dict[str, Any]] = None) -> None:
        """Convenience method to increment a counter."""
        counter = self.create_counter(name)
        counter.add(value, attributes)
    
    def update_updown_counter(self, name: str, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Convenience method to update an up/down counter."""
        counter = self.create_updown_counter(name)
        counter.add(value, attributes)
    
    def record_gauge(self, name: str, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Convenience method to record a gauge value."""
        gauge = self.create_gauge(name)
        gauge.set(value, attributes)
    
    def record_histogram(self, name: str, value: float, attributes: Optional[dict[str, Any]] = None) -> None:
        """Convenience method to record a histogram value."""
        histogram = self.create_histogram(name)
        histogram.record(value, attributes)
    
    # Span methods
    @abstractmethod
    def start_span(self, name: str, attributes: Optional[dict[str, Any]] = None) -> Span:
        """Start a new span."""
        pass
    
    # Context manager for spans
    @contextmanager
    def span(self, name: str, attributes: Optional[dict[str, Any]] = None):
        """Context manager for creating and managing spans."""
        span = self.start_span(name, attributes)
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            span.set_attribute("error.type", type(e).__name__)
            span.end("error")
            raise
        else:
            span.end("ok")
    
    # Decorator for tracing functions
    def trace(self, name: Optional[str] = None, attributes: Optional[dict[str, Any]] = None):
        """Decorator to trace function execution."""
        def decorator(func: Callable):
            span_name = name or f"{func.__module__}.{func.__name__}"
            
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    with self.span(span_name, attributes):
                        return await func(*args, **kwargs)
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    with self.span(span_name, attributes):
                        return func(*args, **kwargs)
                return sync_wrapper
        return decorator
    
    # Timing helpers
    @contextmanager
    def time_histogram(self, name: str, attributes: Optional[dict[str, Any]] = None):
        """Context manager to time operations and record to histogram."""
        histogram = self.create_histogram(name, unit="s")
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            histogram.record(duration, attributes)
    
    def time_function(self, histogram_name: Optional[str] = None, attributes: Optional[dict[str, Any]] = None):
        """Decorator to time function execution."""
        def decorator(func: Callable):
            name = histogram_name or f"{func.__module__}.{func.__name__}.duration"
            
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    with self.time_histogram(name, attributes):
                        return await func(*args, **kwargs)
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    with self.time_histogram(name, attributes):
                        return func(*args, **kwargs)
                return sync_wrapper
        return decorator