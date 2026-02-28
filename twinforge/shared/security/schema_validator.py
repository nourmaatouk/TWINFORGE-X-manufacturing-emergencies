"""
TWINFORGE Schema Validator
Pydantic model validation helper utilities.
"""

import logging
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def validate_payload(data: dict[str, Any], schema: Type[T]) -> tuple[bool, T | None, str]:
    """
    Validate a dict payload against a Pydantic model.

    Returns:
        (is_valid, parsed_model_or_None, error_message)
    """
    try:
        model = schema.model_validate(data)
        return True, model, ""
    except ValidationError as e:
        error_msg = str(e)
        logger.warning("Validation failed for %s: %s", schema.__name__, error_msg)
        return False, None, error_msg


def validate_or_raise(data: dict[str, Any], schema: Type[T]) -> T:
    """Validate and return model, raising ValueError on failure."""
    is_valid, model, error = validate_payload(data, schema)
    if not is_valid or model is None:
        raise ValueError(f"Payload validation failed: {error}")
    return model
