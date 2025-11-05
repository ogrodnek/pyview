# Research: Parameter Conversion in Python Web Frameworks

## Executive Summary

This document explores how various Python web frameworks handle the common problem of converting URL query parameters and form data (typically `dict[str, list[str]]`) into typed Python arguments. The goal is to inform the design of a parameter conversion system for PyView that is:

1. **Flexible**: Supports multiple type hint styles (primitives, TypedDict, dataclasses, Pydantic models)
2. **Ergonomic**: Reduces boilerplate for developers
3. **Testable**: Core conversion logic can be unit tested independently
4. **Incremental**: Can be implemented progressively, starting with simpler types

---

## Current PyView Implementation

### Problem Statement

Currently, PyView developers must manually extract and convert parameters:

```python
async def handle_params(self, url, params, socket: LiveViewSocket[CountContext]):
    if "c" in params:
        socket.context["count"] = int(params["c"][0])  # Manual extraction & conversion!
```

**Why this is burdensome:**
- `params` is `dict[str, list[str]]` from `urllib.parse.parse_qs()`
- Values are always lists, even for single values
- Developers must handle: existence checks, list indexing `[0]`, type conversion, defaults, and error handling

### Current Code Locations

| Component | File | Key Details |
|-----------|------|-------------|
| LiveView base class | `pyview/live_view.py:29-36` | Defines `handle_event` and `handle_params` signatures |
| WebSocket handler | `pyview/ws_handler.py:103-107, 156-171, 214` | Calls these methods with raw params/payload |
| Event dispatcher | `pyview/events/BaseEventHandler.py:50-54` | Routes events to `@event` decorated methods |
| ChangeSet | `pyview/changesets/changesets.py` | Uses Pydantic for form validation (not general params) |

**Key observations:**
- Form payloads go through `parse_qs()` → `dict[str, list[str]]`
- Event payloads can be either dicts or URL-encoded strings (converted to `dict[str, list[str]]`)
- No automatic type coercion exists today
- ChangeSet provides validation for forms only, using Pydantic models

---

## Framework Approaches

### 1. FastAPI (via Pydantic + Dependency Injection)

**Philosophy:** Use Python type hints as the single source of truth for validation and conversion.

**How it works:**

```python
from fastapi import FastAPI, Query
from typing import Optional

app = FastAPI()

# Simple types - automatic conversion
@app.get("/items/")
async def read_items(skip: int = 0, limit: int = 10):
    return {"skip": skip, "limit": limit}

# With Query for more control
@app.get("/items/")
async def read_items(
    q: Optional[str] = Query(None, max_length=50),
    count: list[int] = Query([])
):
    return {"q": q, "count": count}

# Pydantic model as dependency
from pydantic import BaseModel

class FilterParams(BaseModel):
    skip: int = 0
    limit: int = 100
    order_by: Optional[str] = None

@app.get("/items/")
async def read_items(filters: FilterParams = Depends()):
    return filters
```

**Key implementation details:**
1. **Inspection:** Uses `inspect.signature()` to extract parameter names and type annotations
2. **Type conversion:** Delegates to Pydantic for validation and coercion
3. **Error handling:** Returns HTTP 422 with detailed JSON error body if conversion fails
4. **Dependency injection:** `Depends()` can inject complex objects built from query params

**Source code:**
- FastDepends library extracts the DI logic: https://github.com/Lancetnik/FastDepends
- Uses Pydantic V2's validation under the hood

**Pros:**
- Zero boilerplate for common cases
- Excellent error messages
- Supports complex types (lists, unions, nested models)
- Type-safe and IDE-friendly

**Cons:**
- Tightly coupled to Pydantic (though that's also a strength)
- Dependency system adds complexity

---

### 2. Pydantic `validate_call` Decorator

**Philosophy:** Apply Pydantic validation to any function, not just web endpoints.

**How it works:**

```python
from pydantic import validate_call, ValidationError
from datetime import date

@validate_call
def repeat(count: int, message: str) -> str:
    return message * count

# String "4" is automatically converted to int
result = repeat("4", "hello")  # Returns "hellohellohellohello"

@validate_call
def process_date(d1: date, d2: date):
    return (d2 - d1).days

# Strings converted to dates
days = process_date("2000-01-01", "2000-01-10")  # Returns 9
```

**Key features:**
1. **Type coercion by default:** Automatically converts compatible types
2. **Strict mode available:** Set `validate_call(config=ConfigDict(strict=True))` to disable coercion
3. **Standard errors:** Raises `ValidationError` (not `TypeError`) for invalid inputs
4. **Return validation:** Can also validate return values with `validate_return=True`

**Implementation approach:**
```python
# Simplified version of what @validate_call does:
def validate_call(func):
    sig = inspect.signature(func)

    # Create a Pydantic model dynamically from the signature
    fields = {}
    for name, param in sig.parameters.items():
        if param.annotation != inspect.Parameter.empty:
            default = param.default if param.default != inspect.Parameter.empty else ...
            fields[name] = (param.annotation, default)

    # Use the model for validation
    ValidatorModel = create_model(f'{func.__name__}Validator', **fields)

    @wraps(func)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Validate and coerce
        validated = ValidatorModel(**bound.arguments)

        # Call with validated args
        return func(**validated.model_dump())

    return wrapper
```

**Pros:**
- Minimal API surface (just a decorator)
- Leverages Pydantic's mature validation/coercion
- Can be applied to any function
- Great for gradual adoption

**Cons:**
- Requires Pydantic dependency
- Slight performance overhead (but Pydantic V2 is very fast)

---

### 3. Flask + Webargs/Marshmallow

**Philosophy:** Explicitly declare expected parameters with schema objects.

**How it works:**

```python
from flask import Flask
from webargs import fields
from webargs.flaskparser import use_args

app = Flask(__name__)

# Define schema explicitly
user_args = {
    "username": fields.Str(required=True),
    "user_id": fields.Int(required=True),
    "page": fields.Int(missing=1),
    "per_page": fields.Int(missing=20),
    "tags": fields.List(fields.Str()),
}

@app.route("/users")
@use_args(user_args, location="query")
def get_users(args):
    # args is a dict with converted values
    return {
        "username": args["username"],
        "user_id": args["user_id"],
        "page": args["page"],
    }

# Can also use class-based schemas
from marshmallow import Schema

class UserSchema(Schema):
    username = fields.Str(required=True)
    user_id = fields.Int(required=True)
    page = fields.Int(missing=1)

@app.route("/users")
@use_args(UserSchema, location="query")
def get_users(args):
    return args
```

**Key implementation details:**
1. **Marshmallow fields:** Define type, validation, default values, missing values
2. **Location aware:** Can parse from query, json body, headers, cookies, files
3. **Error handling:** Returns HTTP 422 with detailed errors by default
4. **Explicit schema:** More verbose but very flexible

**Field types:**
- Basic: `Str()`, `Int()`, `Float()`, `Bool()`, `Decimal()`
- Complex: `List()`, `Dict()`, `Nested()`, `DateTime()`, `UUID()`
- Custom: `Method()`, `Function()` for custom deserialization

**Pros:**
- Explicit and declarative
- Framework-agnostic (webargs supports many frameworks)
- Mature ecosystem
- Fine-grained control over each field

**Cons:**
- More verbose than type hint approaches
- Requires defining schemas separately from function signatures
- Can feel like duplicate work if you have dataclasses/TypedDicts

---

### 4. Django REST Framework Serializers

**Philosophy:** Serializers as bidirectional converters between complex types and primitive representations.

**How it works:**

```python
from rest_framework import serializers

class UserQuerySerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    page = serializers.IntegerField(default=1, min_value=1)
    per_page = serializers.IntegerField(default=20, min_value=1, max_value=100)
    search = serializers.CharField(required=False, max_length=100)
    is_active = serializers.BooleanField(default=True)

    def validate_user_id(self, value):
        # Custom field validation
        if value < 0:
            raise serializers.ValidationError("user_id must be positive")
        return value

    def validate(self, data):
        # Cross-field validation
        if data['per_page'] > 50 and not data.get('is_active'):
            raise serializers.ValidationError("Large page sizes only for active users")
        return data

# Usage in a view
from rest_framework.views import APIView

class UserListView(APIView):
    def get(self, request):
        serializer = UserQuerySerializer(data=request.query_params)
        if serializer.is_valid():
            # Access validated data
            user_id = serializer.validated_data['user_id']
            page = serializer.validated_data['page']
            # ... use the data
        else:
            return Response(serializer.errors, status=400)
```

**Key features:**
1. **Type coercion:** Fields handle conversion automatically (strings → ints, bools, etc.)
2. **Validation pipeline:** Field validators → field-level `validate_<field>()` → object-level `validate()`
3. **Error accumulation:** Collects all errors, not just the first one
4. **Explicit defaults:** Clear difference between `default` (for missing keys) and `None`

**Boolean coercion example:**
- `'true', 't', 'True', '1'` → `True`
- `'false', 'f', 'False', '0'` → `False`
- Everything else → `bool(value)` (so `'bla'` → `True`)

**Pros:**
- Battle-tested in large Django projects
- Excellent error reporting
- Supports complex validation logic
- Clear separation of concerns

**Cons:**
- Verbose for simple cases
- Tightly coupled to Django REST Framework
- More object-oriented vs. functional style

---

### 5. Type Conversion Libraries

#### A. **cattrs** - Composable converters for attrs/dataclasses

```python
from dataclasses import dataclass
from typing import Optional
import cattrs

@dataclass
class UserParams:
    user_id: int
    page: int = 1
    search: Optional[str] = None

# Unstructure (Python → dict)
params = UserParams(user_id=123, page=2)
data = cattrs.unstructure(params)
# {'user_id': 123, 'page': 2, 'search': None}

# Structure (dict → Python)
params = cattrs.structure({'user_id': '123', 'page': '2'}, UserParams)
# UserParams(user_id=123, page=2, search=None)
```

**Features:**
- Supports: attrs, dataclasses, TypedDict (since v23.1.0)
- Type coercion: Converts strings to appropriate types
- Hooks: Customize conversion with `register_structure_hook`
- Pre-configured converters for JSON, msgpack, YAML, TOML, etc.

#### B. **dacite** - Simple dataclass creation from dicts

```python
from dataclasses import dataclass
from typing import Optional
from dacite import from_dict, Config

@dataclass
class UserParams:
    user_id: int
    page: int = 1
    tags: list[str] = None

data = {
    'user_id': '123',  # String will be converted
    'page': '2',
    'tags': ['python', 'web']
}

params = from_dict(
    data_class=UserParams,
    data=data,
    config=Config(
        type_hooks={int: lambda x: int(x) if isinstance(x, str) else x},
        cast=[list]
    )
)
# UserParams(user_id=123, page=2, tags=['python', 'web'])
```

**Features:**
- Focus: dataclasses only
- Nested dataclasses: Automatically handled
- Optional fields: Default to `None`
- Union types: Tries each type until one works
- Config: Remap keys, transform values, type hooks

#### C. **msgspec** - High-performance validation

```python
import msgspec

class UserParams(msgspec.Struct):
    user_id: int
    page: int = 1
    search: str | None = None

# Strict mode (default) - no implicit conversions
try:
    params = msgspec.convert({'user_id': '123', 'page': 2}, UserParams)
except msgspec.ValidationError:
    pass  # Fails because '123' is a string, not int

# Lax mode - allows safe conversions
params = msgspec.convert(
    {'user_id': '123', 'page': '2'},
    UserParams,
    strict=False
)
# UserParams(user_id=123, page=2, search=None)
```

**Features:**
- **Performance:** 5-60x faster than dataclasses, 17x faster than Pydantic
- **Validation during decode:** Zero-cost validation (faster than decoding to dict then validating)
- **Strict by default:** Explicit about type coercion
- **Multiple formats:** JSON, MessagePack, YAML, TOML

---

## Implementation Patterns

### Pattern 1: Signature Inspection + Type Adapter

This is the most flexible approach, combining Python's `inspect` module with a type conversion library.

```python
import inspect
from typing import get_type_hints, get_origin, get_args
from functools import wraps

def bind_params(func):
    """Decorator that converts dict[str, list[str]] params to typed arguments."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    @wraps(func)
    async def wrapper(self, *args, **raw_kwargs):
        # Assuming raw_kwargs contains the dict[str, list[str]] params
        params = raw_kwargs.get('params', {})

        converted = {}
        for name, param in sig.parameters.items():
            if name in ('self', 'url', 'socket'):
                continue

            hint = hints.get(name, str)

            if name in params:
                raw_value = params[name]
                # Handle list[str] → appropriate type
                converted[name] = convert_value(raw_value, hint)
            elif param.default != inspect.Parameter.empty:
                converted[name] = param.default
            else:
                # Required parameter missing
                raise ValueError(f"Missing required parameter: {name}")

        # Call original function with converted params
        return await func(self, *args, **converted)

    return wrapper

def convert_value(raw_value: list[str], target_type):
    """Convert list[str] to target_type."""
    origin = get_origin(target_type)

    # Handle Optional[T]
    if origin is Union:
        args = get_args(target_type)
        if type(None) in args:
            # Optional type
            if not raw_value or raw_value == ['']:
                return None
            # Get the non-None type
            target_type = next(t for t in args if t is not type(None))
            origin = get_origin(target_type)

    # Handle list[T]
    if origin is list:
        inner_type = get_args(target_type)[0]
        return [convert_scalar(v, inner_type) for v in raw_value]

    # Handle scalar (take first value)
    if raw_value:
        return convert_scalar(raw_value[0], target_type)

    return None

def convert_scalar(value: str, target_type):
    """Convert single string to target_type."""
    if target_type == str:
        return value
    elif target_type == int:
        return int(value)
    elif target_type == float:
        return float(value)
    elif target_type == bool:
        # Handle common boolean representations
        return value.lower() in ('true', 't', '1', 'yes', 'on')
    else:
        # For complex types, delegate to type adapter
        return target_type(value)
```

**Usage:**

```python
class MyLiveView(LiveView):
    @bind_params
    async def handle_params(self, count: int = 0, page: int = 1):
        # count and page are already converted!
        socket.context["count"] = count
        socket.context["page"] = page
```

---

### Pattern 2: Typed Parameter Object

Use a single typed object to represent all parameters, leveraging existing libraries.

```python
from typing import TypedDict, Optional
from dataclasses import dataclass
import cattrs

# Option 1: TypedDict
class CountParams(TypedDict, total=False):
    count: int
    page: int

# Option 2: Dataclass
@dataclass
class CountParams:
    count: int = 0
    page: int = 1

# Option 3: Pydantic
from pydantic import BaseModel

class CountParams(BaseModel):
    count: int = 0
    page: int = 1

# Converter helper
def parse_params(params: dict[str, list[str]], param_type):
    """Convert dict[str, list[str]] to param_type."""
    # Flatten lists (take first value for scalars)
    flat = {}
    for key, values in params.items():
        if values:
            # Check if param_type expects a list for this field
            # For now, just take first value
            flat[key] = values[0]

    # Use cattrs, dacite, or Pydantic to convert
    if hasattr(param_type, 'model_validate'):
        # Pydantic
        return param_type.model_validate(flat)
    else:
        # cattrs for dataclasses/TypedDict
        return cattrs.structure(flat, param_type)

# Usage
async def handle_params(self, url, params, socket):
    typed_params = parse_params(params, CountParams)
    socket.context["count"] = typed_params.count
    socket.context["page"] = typed_params.page
```

**Advantage:** Reuses existing, well-tested libraries.

---

### Pattern 3: Decorator with Magic Signature Matching

Automatically detect whether the user wants individual args or a typed object.

```python
import inspect
from typing import get_type_hints

def smart_params(func):
    """
    Automatically convert params based on function signature.
    Supports:
    - handle_params(self, count: int, page: int)
    - handle_params(self, params: CountParams)
    - handle_params(self, url, params, socket)  # No conversion
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    param_names = list(sig.parameters.keys())

    # Check signature style
    if 'params' in param_names and param_names.index('params') >= 2:
        # Traditional style, check if params has a type hint
        params_param = sig.parameters['params']
        params_hint = hints.get('params')

        if params_hint and params_hint != inspect.Parameter.empty:
            # User wants typed params object
            @wraps(func)
            async def wrapper(self, url, params, socket, *args, **kwargs):
                typed_params = parse_params(params, params_hint)
                return await func(self, url, typed_params, socket, *args, **kwargs)
            return wrapper

    # Check if user wants individual args (no url/params/socket after self)
    non_special_params = [
        p for p in param_names[1:]  # Skip 'self'
        if p not in ('url', 'params', 'socket')
    ]

    if non_special_params:
        # User wants individual args
        @wraps(func)
        async def wrapper(self, url, params, socket, *args, **kwargs):
            converted = {}
            for name in non_special_params:
                param = sig.parameters[name]
                hint = hints.get(name, str)

                if name in params:
                    converted[name] = convert_value(params[name], hint)
                elif param.default != inspect.Parameter.empty:
                    converted[name] = param.default
                else:
                    raise ValueError(f"Missing required parameter: {name}")

            return await func(self, **converted)
        return wrapper

    # No conversion needed, use original signature
    return func
```

**Usage - Multiple styles supported:**

```python
# Style 1: Individual typed args
@smart_params
async def handle_params(self, count: int = 0, page: int = 1):
    pass

# Style 2: Typed params object
@smart_params
async def handle_params(self, url, params: CountParams, socket):
    pass

# Style 3: Traditional (no conversion)
async def handle_params(self, url, params, socket):
    pass
```

---

## Recommendations for PyView

### Phase 1: Core Infrastructure (MVP)

**Goal:** Support simple scalar types and lists with minimal dependencies.

1. **Create `pyview.params` module** with:
   - `convert_value(raw: list[str], target_type: Type) -> Any`
   - `parse_query_params(params: dict[str, list[str]], signature) -> dict`
   - Support for: `str`, `int`, `float`, `bool`, `Optional[T]`, `list[T]`

2. **Add `@typed_params` decorator** that:
   - Uses `inspect.signature()` to get parameter info
   - Calls `parse_query_params()` to convert
   - Passes converted kwargs to the original function

3. **Opt-in usage:**
   ```python
   from pyview.params import typed_params

   class MyView(LiveView):
       @typed_params
       async def handle_params(self, count: int = 0):
           socket.context["count"] = count
   ```

**Why this approach:**
- No external dependencies
- Easy to test in isolation
- Clear migration path (opt-in decorator)
- Covers 80% of use cases

### Phase 2: Rich Type Support

**Goal:** Support TypedDict, dataclasses, and Pydantic models.

1. **Add type adapter abstraction:**
   ```python
   class TypeAdapter(Protocol):
       def structure(self, data: dict, target_type: Type) -> Any:
           ...
   ```

2. **Implement adapters:**
   - `PydanticAdapter` - if pydantic available
   - `CattrsAdapter` - if cattrs available
   - `DaciteAdapter` - if dacite available
   - `BuiltinAdapter` - fallback using constructor

3. **Auto-detect which adapter to use:**
   ```python
   def get_adapter_for(target_type: Type) -> TypeAdapter:
       if isinstance(target_type, type) and issubclass(target_type, BaseModel):
           return PydanticAdapter()
       elif is_dataclass(target_type):
           return CattrsAdapter() if cattrs else DaciteAdapter()
       elif is_typeddict(target_type):
           return CattrsAdapter()
       else:
           return BuiltinAdapter()
   ```

### Phase 3: Advanced Features

1. **Validation errors:** Return structured error responses
2. **List parameters:** Handle `?tags=python&tags=web` → `list[str]`
3. **Nested objects:** Support dot notation `?user.name=John`
4. **Custom converters:** Registry for user-defined type converters
5. **`@event` decorator enhancement:** Apply same logic to event handlers

### Implementation Checklist

- [ ] Create `pyview/params/__init__.py`
- [ ] Implement `convert_scalar()` for basic types
- [ ] Implement `convert_value()` for Optional and list
- [ ] Implement `parse_query_params()` using signature inspection
- [ ] Create `@typed_params` decorator
- [ ] Write unit tests for conversion logic (critical!)
- [ ] Write integration tests with LiveView
- [ ] Document usage in examples
- [ ] Add type adapter abstraction (Phase 2)
- [ ] Implement Pydantic adapter (Phase 2)
- [ ] Implement cattrs/dacite adapters (Phase 2)
- [ ] Support TypedDict and dataclasses (Phase 2)

### Testing Strategy

```python
# tests/test_params.py

def test_convert_scalar_int():
    assert convert_scalar("123", int) == 123

def test_convert_scalar_bool_true():
    assert convert_scalar("true", bool) == True
    assert convert_scalar("1", bool) == True

def test_convert_value_optional_present():
    assert convert_value(["123"], Optional[int]) == 123

def test_convert_value_optional_missing():
    assert convert_value([], Optional[int]) == None

def test_convert_value_list_int():
    assert convert_value(["1", "2", "3"], list[int]) == [1, 2, 3]

def test_parse_query_params_with_defaults():
    def dummy(count: int = 0, page: int = 1): pass
    sig = inspect.signature(dummy)

    result = parse_query_params({"count": ["5"]}, sig)
    assert result == {"count": 5, "page": 1}

def test_parse_query_params_missing_required():
    def dummy(count: int): pass
    sig = inspect.signature(dummy)

    with pytest.raises(ValueError, match="Missing required parameter: count"):
        parse_query_params({}, sig)
```

---

## Alternative Approaches Considered

### Option A: Always require typed object

**Pro:** Consistent, reusable parameter definitions.
**Con:** More verbose for simple cases.

```python
class CountParams(TypedDict):
    count: int

async def handle_params(self, url, params: CountParams, socket):
    pass
```

### Option B: Use dependency injection like FastAPI

**Pro:** Maximum flexibility, supports complex scenarios.
**Con:** Significant complexity, might be overkill for PyView's use cases.

### Option C: Generate code at class registration

**Pro:** Zero runtime overhead.
**Con:** Makes debugging harder, adds complexity.

---

## Conclusion

The recommended approach for PyView is:

1. **Start simple:** Implement decorator-based conversion for scalar types and lists
2. **Use stdlib:** Leverage `inspect.signature()` and `typing` for introspection
3. **Incremental complexity:** Add support for TypedDict/dataclass/Pydantic progressively
4. **Delegate when possible:** Use Pydantic/cattrs for complex types in Phase 2
5. **Make it testable:** Pure functions for conversion logic, easy to unit test
6. **Keep it opt-in:** Don't break existing code, use decorators

This balances developer ergonomics (minimal boilerplate), implementation complexity (start simple, add features incrementally), and alignment with Python's type hinting ecosystem.

### Example of Desired End State

```python
from pyview import LiveView, typed_params
from dataclasses import dataclass

@dataclass
class SearchParams:
    query: str
    page: int = 1
    per_page: int = 20
    tags: list[str] = field(default_factory=list)

class SearchView(LiveView):
    # Style 1: Individual args
    @typed_params
    async def handle_event(self, event, item_id: int, enabled: bool = True, socket):
        # item_id and enabled are already converted!
        pass

    # Style 2: Typed object
    @typed_params
    async def handle_params(self, url, params: SearchParams, socket):
        # params is a SearchParams instance!
        results = search(params.query, params.page, params.per_page)
        pass
```

Clean, type-safe, and testable!
