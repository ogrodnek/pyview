"""
Example: Configurable error handling for @typed_params

This shows how to add error handling strategies to the decorator.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any
import logging

logger = logging.getLogger(__name__)


class ParamErrorStrategy(Enum):
    """Strategy for handling parameter conversion errors."""

    RAISE = "raise"              # Raise exception (current behavior)
    LOG_AND_DEFAULT = "log"      # Log warning and use default value
    IGNORE = "ignore"            # Silently use default value
    # COLLECT = "collect"        # Future: collect errors like ChangeSet


@dataclass
class ParamConversionError:
    """Details about a parameter conversion failure."""
    param_name: str
    raw_value: Any
    expected_type: str
    error: Exception

    def __str__(self):
        return f"Cannot convert '{self.raw_value}' to {self.expected_type} for parameter '{self.param_name}'"


def handle_conversion_error(
    error: ParamConversionError,
    strategy: ParamErrorStrategy,
    default_value: Any = None
) -> Any:
    """
    Handle a parameter conversion error according to the chosen strategy.

    Args:
        error: Details about the conversion failure
        strategy: How to handle the error
        default_value: Default value to use if conversion fails

    Returns:
        The value to use (either raises or returns default)

    Raises:
        ValueError: If strategy is RAISE
    """
    if strategy == ParamErrorStrategy.RAISE:
        raise ValueError(str(error)) from error.error

    elif strategy == ParamErrorStrategy.LOG_AND_DEFAULT:
        logger.warning(
            f"Parameter conversion failed: {error}. Using default: {default_value}",
            extra={
                "param_name": error.param_name,
                "raw_value": error.raw_value,
                "expected_type": error.expected_type,
            }
        )
        return default_value

    elif strategy == ParamErrorStrategy.IGNORE:
        # Silently use default
        return default_value

    else:
        # Unknown strategy, fail safe
        raise ValueError(f"Unknown error strategy: {strategy}")


# Example usage in conversion.py:
"""
def convert_params(
    raw_params: dict[str, Union[str, list[str]]],
    signature: inspect.Signature,
    skip_params: set[str] | None = None,
    on_error: ParamErrorStrategy = ParamErrorStrategy.LOG_AND_DEFAULT,
) -> dict[str, Any]:
    '''Convert with configurable error handling.'''

    if skip_params is None:
        skip_params = set()

    converted = {}

    for param_name, param in signature.parameters.items():
        if param_name in skip_params:
            continue

        target_type = param.annotation

        if param_name in raw_params:
            try:
                converted[param_name] = convert_value(raw_params[param_name], target_type)
            except ValueError as e:
                # Create error details
                error = ParamConversionError(
                    param_name=param_name,
                    raw_value=raw_params[param_name],
                    expected_type=str(target_type),
                    error=e
                )

                # Handle according to strategy
                default = param.default if param.default != inspect.Parameter.empty else None
                converted[param_name] = handle_conversion_error(error, on_error, default)

        elif param.default != inspect.Parameter.empty:
            converted[param_name] = param.default
        else:
            # Required param missing
            if on_error == ParamErrorStrategy.RAISE:
                raise ValueError(f"Missing required parameter: '{param_name}'")
            else:
                # Use None for required params when using graceful strategies
                logger.warning(f"Required parameter '{param_name}' is missing, using None")
                converted[param_name] = None

    return converted
"""
