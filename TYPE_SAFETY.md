# Type Safety for socket.state

## What is State?

`State` is Starlette's simple dictionary wrapper that allows attribute access:

```python
from starlette.datastructures import State

state = State()
state.foo = "bar"  # Sets state._state["foo"] = "bar"
print(state.foo)   # Gets state._state["foo"]
```

**Implementation:**
```python
class State:
    _state: dict[str, Any]  # Just a dict!

    def __setattr__(self, key, value):
        self._state[key] = value

    def __getattr__(self, key):
        return self._state[key]
```

**Key Points:**
- ✅ It's just a dictionary with attribute syntax
- ❌ NOT type-safe by default
- ❌ Everything is `Any` to type checkers
- ✅ Raises `AttributeError` (not `KeyError`) for missing keys

## The Problem

Without type hints, you lose IDE support:

```python
async def mount(self, socket, session):
    # ❌ No autocomplete - IDE doesn't know what's available
    db = socket.state.database

    # ❌ Type checker thinks db is Any
    result = await db.query("SELECT * FROM users")

    # ❌ Typos aren't caught until runtime
    cache = socket.state.chache  # Oops!
```

## The Solution: Type-Safe Service Locator

**One-time setup:**

```python
from starlette.datastructures import State

# 1. Define your services
class Database:
    async def get_user(self, user_id: int) -> dict:
        ...

class Cache:
    async def get(self, key: str) -> str | None:
        ...

# 2. Create type-safe wrapper
class Services:
    def __init__(self, state: State):
        self._state = state

    @property
    def database(self) -> Database:
        return self._state.database

    @property
    def cache(self) -> Cache:
        return self._state.cache

# 3. Helper function
def services(socket) -> Services:
    return Services(socket.state)
```

**Use everywhere:**

```python
async def mount(self, socket, session):
    # Get type-safe services
    svc = services(socket)

    # ✅ IDE autocompletes methods
    # ✅ Type checker knows this is Database, not Any
    # ✅ Method signatures are validated
    user = await svc.database.get_user(session["user_id"])
    cached = await svc.cache.get(f"user:{user['id']}")
```

## Benefits

| Feature | Without Types | With Service Locator |
|---------|--------------|---------------------|
| Autocomplete | ❌ No | ✅ Yes |
| Type Checking | ❌ Everything is Any | ✅ Proper types |
| Catch Typos | ❌ Runtime | ✅ Dev time |
| Refactoring | ❌ Manual | ✅ IDE-assisted |
| Documentation | ❌ Check code | ✅ Types are docs |

## Testing Still Simple

Mocks work exactly the same:

```python
@pytest.mark.asyncio
async def test_my_view():
    # Create mock (with spec for type safety!)
    mock_db = Mock(spec=Database)
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test"})

    # Inject as usual
    socket = UnconnectedSocket()
    socket.state.database = mock_db

    # ✅ Still type-safe in tests!
    svc = services(socket)
    user = await svc.database.get_user(1)
```

## Alternative Approaches

### 1. Direct Type Annotations
```python
async def mount(self, socket, session):
    db: Database = socket.state.database  # Type hint
    cache: Cache = socket.state.cache
```

**Pros:** Simple
**Cons:** Manual hints, no autocomplete before assignment

### 2. Protocol-Based
```python
from typing import Protocol

class HasDatabase(Protocol):
    database: Database

def get_db(socket: HasDatabase) -> Database:
    return socket.state.database
```

**Pros:** Flexible
**Cons:** More boilerplate per service

### 3. TypedDict (Documentation Only)
```python
from typing import TypedDict, cast

class StateDict(TypedDict):
    database: Database
    cache: Cache

state = cast(StateDict, socket.state._state)
db = state["database"]
```

**Pros:** Simple
**Cons:** No runtime safety, dict syntax

## Recommendation

**Use the Service Locator pattern** (Solution in this doc):

```python
svc = services(socket)
db = svc.database  # Type-safe!
```

**Why:**
- ✅ Best IDE experience (autocomplete everywhere)
- ✅ Strong type checking
- ✅ Clean, readable code
- ✅ One-time setup, use everywhere
- ✅ No runtime overhead
- ✅ Works great with testing

## Complete Example

See `examples/type_safe_demo.py` for a working example showing:
- Service locator setup
- Usage in LiveViews
- Testing with mocks
- Full type safety

Run it:
```bash
poetry run python examples/type_safe_demo.py
```

## Summary

**State is just a dict** - great for flexibility, but loses type safety.

**Add type safety with a simple wrapper:**
1. Create `Services` class with `@property` methods
2. Use `services(socket)` helper
3. Enjoy full IDE support and type checking

**Zero runtime cost, huge developer experience improvement!**
