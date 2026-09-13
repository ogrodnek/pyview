# Prototype spike (not part of the pyview package)

Runnable evidence for Part 4 / Part 7 of the report. Run from the repo root with the project venv:

```
uv run python research/forms/prototype/exp1_pydantic_errors.py   # pydantic loc / coercion facts
uv run python research/forms/prototype/exp2_coercion.py          # form-string coercion table, timing
uv run python research/forms/prototype/exp3_ibis.py              # Ibis renders the field accessor syntax
uv run python research/forms/prototype/exp4_field_targeted_errors.py
uv run python research/forms/prototype/test_proto.py             # v1: decoder + gating + union loc mapping
uv run python research/forms/prototype/test_proto2.py            # v2: row keys, intents, shelf (superseded by v3)
uv run python research/forms/prototype/test_proto3.py            # v3: the corrected semantics from Part 4
```

`pyview_forms_proto3.py` is the reference for the proposal (`Params`, `Form`, `Field.html`, `cast`, `wire`); v1/v2 are kept because Part 7 cites their outputs.
