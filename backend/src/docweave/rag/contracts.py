"""Dependency-free preparation and provider value contracts."""

import math


MAX_BYTES = 20 * 1024 * 1024
MAX_CHARS = 2_000_000
CONFIGURATION = "utf8-lf:headings:whitespace350-overlap50:v1"

class RetrievalError(Exception):
    pass

class HostedError(Exception):
    pass

def validate_vector(vector):
    if not isinstance(vector, list) or len(vector) != 768:
        raise RetrievalError("invalid_vector")
    if any(type(value) not in (float, int) or abs(value) > 1.0001 or not math.isfinite(value) for value in vector):
        raise RetrievalError("invalid_vector")
    if not math.isclose(sum(value * value for value in vector), 1, rel_tol=0.0001):
        raise RetrievalError("invalid_vector")

def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result
