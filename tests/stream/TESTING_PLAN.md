# PyView Streams - Unit Testing Plan

## Testing Strategy

### Test Levels
1. **Unit Tests** - Individual Stream class methods and socket operations
2. **Integration Tests** - Stream + socket + diff generation
3. **Template Tests** - Stream iteration in templates

### Testing Framework
- **pytest** (existing framework in pyview)
- Simple assertions without heavy mocking
- Focus on data transformations and wire protocol correctness

---

## 1. Stream Class Unit Tests

### File: `tests/stream/test_stream_class.py`

#### 1.1 Initialization Tests
- ✅ Initialize with attribute name dom_id
- ✅ Initialize with function dom_id
- ✅ Initialize with default dom_id="id"
- ✅ Verify ref is generated correctly
- ✅ Verify name is optional

**Test Cases:**
```python
def test_stream_init_with_attribute_name()
def test_stream_init_with_function()
def test_stream_init_default()
def test_stream_ref_is_unique()
def test_stream_name_optional()
```

#### 1.2 DOM ID Extraction Tests
- ✅ Extract ID from dataclass with attribute name
- ✅ Extract ID from dict with attribute name
- ✅ Extract ID using custom function
- ✅ Handle missing attribute gracefully

**Test Cases:**
```python
def test_dom_id_from_dataclass_attribute()
def test_dom_id_from_dict_attribute()
def test_dom_id_from_custom_function()
def test_dom_id_missing_attribute_raises_error()
```

#### 1.3 Insert Operations Tests
- ✅ Prepend single item
- ✅ Append single item
- ✅ Insert at specific position
- ✅ Insert with limit parameter
- ✅ Insert with update_only flag
- ✅ Method chaining works
- ✅ Multiple inserts are tracked in order

**Test Cases:**
```python
def test_prepend_single_item()
def test_append_single_item()
def test_insert_at_position()
def test_insert_with_limit()
def test_insert_with_update_only()
def test_insert_method_chaining()
def test_multiple_inserts_tracked()
```

#### 1.4 Bulk Operations Tests
- ✅ Extend with list of items
- ✅ Extend at beginning
- ✅ Extend at end
- ✅ Extend empty list

**Test Cases:**
```python
def test_extend_items()
def test_extend_at_beginning()
def test_extend_at_end()
def test_extend_empty_list()
```

#### 1.5 Update Operations Tests
- ✅ Update existing item
- ✅ Update sets update_only flag

**Test Cases:**
```python
def test_update_item()
def test_update_sets_update_only_flag()
```

#### 1.6 Delete Operations Tests
- ✅ Remove item by object
- ✅ Remove by DOM ID
- ✅ Multiple removes tracked
- ✅ Method chaining works

**Test Cases:**
```python
def test_remove_item_by_object()
def test_remove_by_dom_id()
def test_multiple_removes_tracked()
def test_remove_method_chaining()
```

#### 1.7 Reset Operations Tests
- ✅ Reset clears operations
- ✅ Reset with new items
- ✅ Reset empty
- ✅ Reset flag is set

**Test Cases:**
```python
def test_reset_clears_operations()
def test_reset_with_new_items()
def test_reset_empty()
def test_reset_flag_set()
```

#### 1.8 Iteration Tests
- ✅ Iterate yields (dom_id, item) tuples
- ✅ Iterate over initial items
- ✅ Iterate over pending inserts
- ✅ Iterate over both initial and pending
- ✅ Empty stream iteration

**Test Cases:**
```python
def test_iteration_yields_tuples()
def test_iterate_initial_items()
def test_iterate_pending_inserts()
def test_iterate_initial_and_pending()
def test_empty_stream_iteration()
```

#### 1.9 Operation Consumption Tests
- ✅ has_operations() returns correct state
- ✅ consume_operations() returns correct format
- ✅ consume_operations() clears pending operations
- ✅ Operations are in correct order after consume
- ✅ Initial items cleared after consume

**Test Cases:**
```python
def test_has_operations_true_with_inserts()
def test_has_operations_true_with_deletes()
def test_has_operations_true_with_reset()
def test_has_operations_false_when_empty()
def test_consume_operations_format()
def test_consume_operations_clears_pending()
def test_consume_operations_order()
def test_consume_clears_initial_items()
```

#### 1.10 Edge Cases Tests
- ✅ Operations on empty stream
- ✅ Very large number of operations
- ✅ Same item inserted multiple times
- ✅ Delete non-existent item
- ✅ Complex dom_id functions

**Test Cases:**
```python
def test_operations_on_empty_stream()
def test_many_operations()
def test_duplicate_inserts()
def test_delete_nonexistent_item()
def test_complex_dom_id_function()
```

---

## 2. Socket Integration Tests

### File: `tests/stream/test_socket_integration.py`

#### 2.1 Stream Detection Tests
- ✅ Find streams in dataclass context
- ✅ Find streams in dict context
- ✅ Find multiple streams
- ✅ Handle context without streams
- ✅ Set stream names automatically

**Test Cases:**
```python
def test_find_streams_in_dataclass()
def test_find_streams_in_dict()
def test_find_multiple_streams()
def test_no_streams_in_context()
def test_stream_names_set_automatically()
```

#### 2.2 Diff Generation Tests
- ✅ Diff includes stream operations
- ✅ Diff without stream operations
- ✅ Diff with multiple streams
- ✅ Regular diff fields preserved
- ✅ Stream operations cleared after consume

**Test Cases:**
```python
def test_diff_includes_stream_operations()
def test_diff_without_stream_operations()
def test_diff_with_multiple_streams()
def test_diff_preserves_regular_fields()
def test_stream_operations_cleared_after_diff()
```

#### 2.3 Wire Protocol Format Tests
- ✅ Stream format matches Phoenix protocol
- ✅ Insert entries formatted correctly
- ✅ Delete IDs formatted correctly
- ✅ Reset flag included
- ✅ Stream ref included

**Test Cases:**
```python
def test_wire_protocol_structure()
def test_insert_entry_format()
def test_delete_ids_format()
def test_reset_flag_format()
def test_stream_ref_included()
```

---

## 3. Wire Protocol Correctness Tests

### File: `tests/stream/test_wire_protocol.py`

#### 3.1 Complete Wire Format Tests
- ✅ Full diff with stream insert
- ✅ Full diff with stream delete
- ✅ Full diff with stream reset
- ✅ Full diff with mixed operations
- ✅ Multiple streams in one diff

**Test Cases:**
```python
def test_wire_format_insert_operation()
def test_wire_format_delete_operation()
def test_wire_format_reset_operation()
def test_wire_format_mixed_operations()
def test_wire_format_multiple_streams()
```

#### 3.2 Phoenix Compatibility Tests
- ✅ Format matches Phoenix LiveView 0.18.3+
- ✅ Insert tuple structure: [dom_id, at, limit, update_only]
- ✅ Stream array structure: [ref, inserts, deletes, reset]
- ✅ Stream key is "stream" (not "s" or other)

**Test Cases:**
```python
def test_phoenix_insert_tuple_structure()
def test_phoenix_stream_array_structure()
def test_phoenix_stream_key_name()
def test_phoenix_compatibility_insert()
def test_phoenix_compatibility_delete()
```

---

## 4. Template Integration Tests

### File: `tests/stream/test_stream_template.py`

#### 4.1 Template Iteration Tests
- ✅ Stream iterates in for loop
- ✅ Yields (dom_id, item) tuples
- ✅ Can unpack in template
- ✅ Access item properties after unpack

**Test Cases:**
```python
def test_stream_in_for_loop()
def test_yields_dom_id_item_tuples()
def test_unpack_in_template()
def test_access_item_properties()
```

---

## 5. Integration/E2E Tests (Optional)

### File: `tests/stream/test_stream_e2e.py`

#### 5.1 Complete Flow Tests
- ✅ Mount → Render → Insert → Diff
- ✅ Mount → Render → Delete → Diff
- ✅ Mount → Render → Reset → Diff
- ✅ Multiple operations in sequence

**Test Cases:**
```python
def test_complete_insert_flow()
def test_complete_delete_flow()
def test_complete_reset_flow()
def test_multiple_operations_flow()
```

---

## Test Data Fixtures

### Common Test Models

```python
# tests/stream/conftest.py

from dataclasses import dataclass
from pyview import Stream
import pytest

@dataclass
class Message:
    id: int
    text: str
    user: str

@dataclass
class User:
    id: int
    name: str
    email: str

@pytest.fixture
def sample_messages():
    return [
        Message(id=1, text="Hello", user="Alice"),
        Message(id=2, text="World", user="Bob"),
        Message(id=3, text="Test", user="Charlie"),
    ]

@pytest.fixture
def empty_stream():
    return Stream[Message](dom_id=lambda m: f"msg-{m.id}")

@pytest.fixture
def populated_stream(sample_messages):
    stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    stream.extend(sample_messages)
    return stream
```

---

## Coverage Goals

- **Stream Class**: 95%+ coverage
- **Socket Integration**: 90%+ coverage
- **Wire Protocol**: 100% coverage (critical for compatibility)
- **Template Integration**: 80%+ coverage

---

## Test Execution

```bash
# Run all stream tests
pytest tests/stream/ -v

# Run with coverage
pytest tests/stream/ --cov=pyview.stream --cov=pyview.live_socket --cov-report=term-missing

# Run specific test file
pytest tests/stream/test_stream_class.py -v

# Run specific test
pytest tests/stream/test_stream_class.py::test_prepend_single_item -v
```

---

## Test Priority

### High Priority (Must Have)
1. ✅ Stream basic operations (insert, delete, update)
2. ✅ Wire protocol format correctness
3. ✅ Socket diff generation with streams
4. ✅ DOM ID extraction from different types

### Medium Priority (Should Have)
1. ✅ Edge cases and error handling
2. ✅ Multiple streams in context
3. ✅ Operation ordering
4. ✅ Template iteration

### Low Priority (Nice to Have)
1. ✅ Performance tests
2. ✅ Complex scenarios
3. ✅ Integration tests with real WebSocket

---

## Continuous Testing

### Pre-commit Hooks
- Run stream tests before commit
- Ensure coverage doesn't drop

### CI/CD Integration
- Run full test suite on PR
- Generate coverage reports
- Block merge if tests fail

---

## Example Test Output

```
tests/stream/test_stream_class.py::test_prepend_single_item PASSED
tests/stream/test_stream_class.py::test_append_single_item PASSED
tests/stream/test_stream_class.py::test_insert_at_position PASSED
tests/stream/test_socket_integration.py::test_diff_includes_stream_operations PASSED
tests/stream/test_wire_protocol.py::test_phoenix_insert_tuple_structure PASSED

======================== 45 passed in 0.23s =========================
```
