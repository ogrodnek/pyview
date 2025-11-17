# PyView Architecture & Code Review

**Date:** November 2025
**Reviewer:** Claude
**Focus:** Quick wins and incremental improvements

## Executive Summary

PyView is a well-architected, production-capable Python implementation of Phoenix LiveView with clean separation of concerns, strong typing, and modern Python practices. The codebase shows thoughtful design decisions and innovative features (especially the upload system). However, there are several "quick win" opportunities for improvement.

**Overall Assessment:** 7.5/10 - Solid foundation with room for polish

---

## Architecture Strengths

### 1. **Clean Architecture** ✅
- Clear separation: LiveView → Socket → Handler → Transport
- Protocol-based extensibility (AuthProvider, InstrumentationProvider)
- Type-safe with generics throughout

### 2. **Innovative Upload System** ✅
- Dual-mode: internal (traditional) + external (direct-to-cloud)
- Production-ready S3 integration with presigned URLs
- Excellent documentation (external-uploads.md)

### 3. **Efficient Rendering** ✅
- Smart tree-based diff algorithm minimizes WebSocket traffic
- Special handling for loops and conditionals
- Clean separation of static vs dynamic content

### 4. **Modern Python** ✅
- Python 3.11-3.14 support
- Async/await throughout
- TypedDict for context typing
- Pattern matching (Python 3.10+)

### 5. **Good Developer Experience** ✅
- Auto-discovery of templates
- CLI for scaffolding (`pv create-view`)
- 13 comprehensive examples
- Strong IDE autocomplete via type hints

---

## Quick Wins (Ordered by Priority)

### Priority 1: High Impact, Low Effort

#### 1.1 **Add Ruff Linter** ⚡ (15 minutes)
**Issue:** Justfile references `ruff format` but ruff isn't in dependencies. No linting in CI.

**Why:** Ruff is 10-100x faster than flake8/pylint and includes auto-fixing.

**Action:**
```toml
# Add to pyproject.toml [tool.poetry.group.dev.dependencies]
ruff = "^0.8.0"

# Add configuration
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
]
ignore = ["E501"]  # line too long (handled by formatter)

[tool.ruff.lint.isort]
known-first-party = ["pyview"]
```

**Add to CI (.github/workflows/test.yml):**
```yaml
- name: Lint with ruff
  run: |
    poetry run ruff check .
    poetry run ruff format --check .
```

#### 1.2 **Fix Broad Exception Handling** ⚡ (30 minutes)
**Issue:** Several `except Exception:` catches that hide errors.

**Locations:**
- `ws_handler.py:132` - Catches all exceptions without specific handling
- `live_socket.py:149, 154, 264, 268` - Silent exception suppression
- `uploads.py` - Various broad catches

**Action:**
```python
# Bad (current)
except Exception:
    logger.exception("Unexpected error")
    raise

# Good (specific)
except (WebSocketDisconnect, AuthException) as e:
    logger.warning(f"Connection closed: {e}")
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise
```

**Impact:** Better error messages, easier debugging, prevents hiding bugs.

#### 1.3 **Update Pinned Dependencies** ⚡ (5 minutes)
**Issue:** Black is pinned to old version (24.3.0 from March 2024).

**Action:**
```toml
# Change from:
black = "24.3.0"

# To (if keeping black):
black = "^24.3.0"

# Or better, remove black entirely and use ruff format
```

Current versions you could safely update to:
- black: 24.11.0 (if keeping it)
- pyright: 1.1.391 → latest
- starlette: 0.50.0 → check for 0.51+

#### 1.4 **Address TODO Comments** ⚡ (1-2 hours)
**Issue:** 6 TODO comments in production code indicating technical debt.

**Quick wins:**

```python
# pyview/live_view.py:18
# TODO: ideally this would always be a ParseResult, but we need to update push_patch
```
**Fix:** Standardize on `ParseResult` throughout. Update `push_patch` to accept ParseResult.

```python
# pyview/ws_handler.py:207
# TODO: I don't think this is actually going to work...
```
**Fix:** This is in path parameter extraction during live_patch. Add a test case and either fix or document why it's okay.

```python
# pyview/live_socket.py:178
# TODO another way to marshall this
```
**Fix:** The params dict manipulation is hacky. Create a proper `_normalize_params()` helper.

#### 1.5 **Remove Dead Code** ⚡ (10 minutes)
**Issue:** `ConnectionManager` class in ws_handler.py is essentially a pass-through.

```python
# Current (pyview/ws_handler.py:391-399)
class ConnectionManager:
    def __init__(self):
        pass

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
```

**Action:** Remove the class and call `websocket.accept()` and `websocket.send_text()` directly. This simplifies the code and removes unnecessary indirection.

---

### Priority 2: Medium Impact, Low-Medium Effort

#### 2.1 **Add Missing Docstrings** 📝 (2-3 hours)
**Issue:** Many public methods lack docstrings, especially in core classes.

**Action:** Add docstrings to public APIs (following Google or NumPy style):

```python
class LiveView(Generic[T]):
    """Base class for LiveView components.

    LiveView enables dynamic, real-time web applications using server-rendered
    HTML and WebSocket communication. Inherit from this class and implement
    lifecycle methods to create interactive views.

    Type Parameters:
        T: TypedDict defining the shape of the view's context/state

    Example:
        >>> class CountContext(TypedDict):
        ...     count: int
        ...
        >>> class CountView(LiveView[CountContext]):
        ...     async def mount(self, socket, session):
        ...         socket.context = {"count": 0}
    """

    async def mount(self, socket: LiveViewSocket[T], session: Session):
        """Initialize view state when a user first connects.

        Called once when the LiveView is first rendered (HTTP request) and
        again when the WebSocket connection is established.

        Args:
            socket: The LiveView socket for managing state and communication
            session: User session data (cookies, authentication, etc.)

        Example:
            >>> async def mount(self, socket, session):
            ...     user_id = session.get("user_id")
            ...     socket.context = {"user_id": user_id, "data": []}
        """
        pass
```

**Priority methods:**
- `LiveView`: mount, handle_event, handle_info, handle_params
- `ConnectedLiveViewSocket`: push_patch, push_navigate, allow_upload, subscribe
- `PyView.add_live_view`

#### 2.2 **Add Basic Unit Tests** 🧪 (3-4 hours)
**Current:** ~296 lines of tests for ~2,800 lines of code (~10% coverage)

**Quick test additions:**

1. **live_socket.py** - Test socket state management
2. **csrf.py** - Test token generation/validation (currently has tests but could expand)
3. **session.py** - Test serialization/deserialization
4. **uploads.py** - Test constraint validation
5. **phx_message.py** - Test message parsing

**Example:**
```python
# tests/test_live_socket.py
import pytest
from pyview import ConnectedLiveViewSocket, UnconnectedSocket

def test_unconnected_socket_is_not_connected():
    socket = UnconnectedSocket()
    assert socket.connected == False

def test_diff_on_first_render_returns_full_tree():
    # ... test diff logic

# tests/test_session.py
def test_serialize_deserialize_session():
    session = {"user_id": 123, "name": "Alice"}
    serialized = serialize_session(session)
    deserialized = deserialize_session(serialized)
    assert deserialized == session
```

**Goal:** Get to 30-40% coverage with basic tests. Don't aim for perfection, just cover critical paths.

#### 2.3 **Add Pre-commit Hooks** ⚡ (30 minutes)
**Why:** Catch issues before CI, faster feedback.

**Action:** Add `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/RobertCraigie/pyright-python
    rev: v1.1.391
    hooks:
      - id: pyright
```

Add to dev dependencies:
```toml
pre-commit = "^3.5.0"
```

#### 2.4 **Improve Error Messages** 💬 (1-2 hours)
**Issue:** Generic error messages make debugging harder.

**Examples:**

```python
# pyview/live_routes.py - When route not found
# Current:
raise ValueError(f"No route found for {path}")

# Better:
available_routes = ", ".join(self.routes.keys())
raise ValueError(
    f"No route found for '{path}'. Available routes: {available_routes}"
)
```

```python
# pyview/csrf.py - When CSRF validation fails
# Current:
raise AuthException("Invalid CSRF token")

# Better:
logger.warning(f"CSRF validation failed for topic: {topic[:20]}...")
raise AuthException(
    "Invalid CSRF token. This may indicate a stale session or "
    "a misconfigured proxy. Try refreshing the page."
)
```

#### 2.5 **Add Type Return Annotations** 📐 (1 hour)
**Issue:** Some functions lack return type hints.

**Examples:**
```python
# pyview/template/utils.py
def find_associated_file(m: LiveView, extension: str):  # Missing -> Optional[str]
    ...

# pyview/uploads.py
def parse_entries(entries: list[dict]):  # Missing -> list[UploadEntry]
    ...
```

**Action:** Run pyright and add missing return types where flagged.

---

### Priority 3: Lower Effort Documentation

#### 3.1 **Create CONTRIBUTING.md** 📄 (30 minutes)
**Why:** Makes it easier for others (and future you) to contribute.

**Contents:**
- Development setup (poetry install)
- Running tests (just test)
- Code style (ruff)
- PR checklist
- Release process

#### 3.2 **Add API Reference Docs** 📚 (2-3 hours)
**Why:** Currently relies heavily on examples. API reference would help.

**Action:** Use mkdocstrings to auto-generate from docstrings:

```yaml
# mkdocs.yml
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [pyview]
          options:
            show_source: true
            show_root_heading: true
```

Add markdown files:
- `docs/api/liveview.md`
- `docs/api/socket.md`
- `docs/api/uploads.md`

#### 3.3 **Improve README Examples** 📖 (1 hour)
**Current README is good but could add:**
- Quick "features" section (uploads, pub/sub, forms, etc.)
- Comparison with similar frameworks
- Link to cookiecutter template more prominently
- Badges (CI status, coverage, PyPI version, Python versions)

**Example additions:**
```markdown
## Features

- 🚀 **Real-time Updates** - Server-driven UI updates via WebSocket
- 📁 **File Uploads** - Internal and external (S3/GCS) upload support
- 📢 **Pub/Sub** - Multi-user real-time features
- ✅ **Form Validation** - Pydantic-based changesets
- 🔐 **Authentication** - Pluggable auth providers
- 📊 **Instrumentation** - Built-in metrics and tracing hooks
- 🎨 **Template Engine** - Fast, type-safe templating
```

---

### Priority 4: Architecture Improvements (Longer-term)

#### 4.1 **Standardize Async Patterns** 🏗️ (Ongoing)
**Observation:** Mix of patterns for async operations.

**Consideration:**
- All I/O should be async (good ✅)
- Consider structured concurrency with `anyio` for complex operations
- Document async best practices in CONTRIBUTING.md

#### 4.2 **Error Recovery Strategy** 🏗️ (Design needed)
**Current:** Limited error recovery in WebSocket handler.

**Future consideration:**
- Reconnection logic
- State recovery after disconnects
- Graceful degradation

#### 4.3 **Rate Limiting** 🔒 (Design needed)
**Missing:** No built-in rate limiting for events or uploads.

**Future:** Add middleware or socket-level rate limiting to prevent abuse.

#### 4.4 **Monitoring Dashboard** 📊 (Nice-to-have)
**Current:** Instrumentation hooks exist but no default implementation.

**Future:**
- Example Prometheus/Grafana setup
- Default OpenTelemetry instrumentation
- Built-in debug panel (development mode)

---

## Code Quality Metrics

### Current State
- **Lines of Code:** ~2,800 (excluding vendor)
- **Test Coverage:** ~10% (est. 296 test lines / 2800 code lines)
- **Type Coverage:** ~90% (good!)
- **Python Support:** 3.11-3.14 ✅
- **CI/CD:** GitHub Actions ✅
- **Documentation:** Basic (README + 1 guide)

### After Quick Wins (Achievable in 1-2 weeks of part-time work)
- **Test Coverage:** 30-40%
- **Linting:** Ruff integrated ✅
- **Type Coverage:** 95%
- **Documentation:** API reference + CONTRIBUTING
- **Code Quality:** Pre-commit hooks

---

## Prioritized Action Plan

### Week 1 (4-6 hours)
1. ✅ Add ruff to dependencies and pyproject.toml (15 min)
2. ✅ Update dependencies (black, pyright) (5 min)
3. ✅ Remove ConnectionManager dead code (10 min)
4. ✅ Fix 2-3 TODO comments (1-2 hours)
5. ✅ Add pre-commit hooks (30 min)
6. ✅ Create CONTRIBUTING.md (30 min)
7. ✅ Add basic docstrings to LiveView and Socket (1-2 hours)

### Week 2 (4-6 hours)
1. ✅ Add 10-15 basic unit tests (3-4 hours)
2. ✅ Fix broad exception handling in ws_handler (30 min)
3. ✅ Improve error messages (1 hour)
4. ✅ Add missing return type annotations (1 hour)

### Week 3 (4-6 hours)
1. ✅ Set up mkdocstrings for API docs (1 hour)
2. ✅ Write API reference pages (2-3 hours)
3. ✅ Add README badges and features section (1 hour)
4. ✅ Address remaining TODOs (1-2 hours)

### Ongoing
- Add tests as you add features
- Review new PRs for docstrings and types
- Keep dependencies updated monthly

---

## Specific File Recommendations

### High Priority Files to Improve

1. **ws_handler.py** (400 lines)
   - Split into smaller functions (handle_connected is 240 lines!)
   - Extract event handlers into separate methods
   - Better error handling

2. **live_socket.py** (274 lines)
   - Add comprehensive docstrings
   - Standardize param handling (fix TODO)
   - More unit tests

3. **uploads.py**
   - Good overall but needs tests
   - Some broad exception catches to fix
   - Could use more inline comments explaining S3 flow

4. **pyview.py** (90 lines)
   - Short and clean! ✅
   - Just needs docstrings

### Files That Are Great
- `render_diff.py` - Clean, focused, well-tested ✅
- `csrf.py` - Simple, tested ✅
- `meta.py` - Minimal, clear ✅

---

## Security Considerations

### Current State
- ✅ CSRF protection implemented
- ✅ Session signing with itsdangerous
- ✅ Auth provider framework
- ⚠️ No rate limiting
- ⚠️ Upload constraints rely on client-side validation
- ⚠️ No input sanitization documentation

### Quick Wins
1. Document security best practices in README
2. Add rate limiting example
3. Show XSS prevention in templates
4. Document secure S3 upload configuration

---

## Dependencies Review

### Current Dependencies (All reasonable ✅)
- `starlette` ^0.50.0 - Solid choice
- `uvicorn` ^0.38.0 - Standard
- `APScheduler` ^3.11.0 - Mature, well-tested
- `pydantic` ^2.9.2 - Modern, type-safe

### Suggestions
- Consider `anyio` for structured concurrency (optional)
- Consider `limits` or `slowapi` for rate limiting (future)
- All versions are recent and well-maintained ✅

---

## Conclusion

PyView is a **well-designed framework** with solid architecture and innovative features. The codebase shows experience and thoughtful design decisions. The quick wins outlined above are mostly polish - improving developer experience, testing, and documentation rather than fixing fundamental issues.

**Recommended Focus:**
1. Testing (biggest gap)
2. Documentation (docstrings + API reference)
3. Linting/tooling (ruff, pre-commit)
4. Code cleanup (TODOs, error handling)

All of these can be tackled incrementally in small chunks, perfect for limited time availability.

**Overall:** This is a project to be proud of! The quick wins will make it even better. 🚀
