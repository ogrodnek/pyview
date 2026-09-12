"""Prototype part 2: row keys, list intents (add/remove/move) and the union 'shelf'.
Builds on pyview_forms_proto.Form; simulates the Phoenix 0.20.17 client: a named <button type=button>
that dispatches a change event is serialised as submitter name/value inside the phx-change payload."""
from __future__ import annotations
import itertools, types, typing
from typing import Any, get_args, get_origin, Union
from pydantic import BaseModel
from pyview_forms_proto import Form as _Form, Field as _Field, decode_form, normalize_empty, humanize, _unwrap_model, _indexed_dicts_to_lists
from pydantic import ValidationError

_counter = itertools.count(1)
def new_key() -> str:
    return f"k{next(_counter)}"

INTENT = "_intent"
KEY = "_key"


class Form(_Form):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.shelf: dict[tuple, dict[str, dict]] = {}   # union path -> {tag: params subtree}

    # ---------------------------------------------------------------- events
    def validate(self, pairs):
        data, meta = decode_form(pairs)
        payload = data.get(self.as_, {})
        target = meta.get("_target")
        if target and target[0] == self.as_:
            self.used.add(target[1:])
        payload = _indexed_dicts_to_lists(self._apply_intents(payload, ()))
        payload = self._apply_shelf(payload, (), self.model_cls)
        self._assign_keys(payload, (), self.model_cls)
        self.params = payload
        self._run()
        return self

    def submit(self, pairs):
        data, _ = decode_form(pairs)
        payload = data.get(self.as_, {})
        payload = _indexed_dicts_to_lists(self._apply_intents(payload, ()))
        payload = self._apply_shelf(payload, (), self.model_cls)
        self._assign_keys(payload, (), self.model_cls)
        self.params = payload
        self.submitted = True
        self._run()
        return self

    def _run(self):
        self.errors = []
        self.model = None
        try:
            self.model = self.model_cls.model_validate(normalize_empty(_strip_meta(self.params)))
        except ValidationError as e:
            self.errors = [humanize(x) for x in e.errors(include_url=False)]

    # ---------------------------------------------------------------- intents
    def _apply_intents(self, node, path):
        """Walk params; a list subtree may carry {'_intent': 'add' | 'remove:<key>' | 'move:<key>:up|down'}
        (sent as the submitter button's name/value). Apply it and strip it."""
        if isinstance(node, dict):
            intent = node.pop(INTENT, None)
            rows_key = None
            if intent is not None:
                # the intent sits on the list's own dict ({'_intent': ..., '0': {...}}) -> rows are the digit keys
                rows = [node[k] for k in sorted((k for k in node if k.isdigit()), key=int)]
                rows = self._mutate(rows, intent, path)
                self.used.add(path)
                node = {str(i): r for i, r in enumerate(rows)}
            return {k: self._apply_intents(v, path + (k if not k.isdigit() else int(k),)) for k, v in node.items()}
        if isinstance(node, list):
            return [self._apply_intents(v, path + (i,)) for i, v in enumerate(node)]
        return node

    def _mutate(self, rows: list, intent: str, path):
        op, *args = intent.split(":")
        if op == "add":
            rows.append({KEY: new_key()})
        elif op == "remove":
            rows = [r for r in rows if not (isinstance(r, dict) and r.get(KEY) == args[0])]
        elif op == "move":
            key, direction = args
            i = next((n for n, r in enumerate(rows) if isinstance(r, dict) and r.get(KEY) == key), None)
            j = i - 1 if direction == "up" else i + 1
            if i is not None and 0 <= j < len(rows):
                rows[i], rows[j] = rows[j], rows[i]
        return rows

    # ---------------------------------------------------------------- keys
    def _assign_keys(self, node, path, ann):
        """Give every list-of-model row a stable _key (kept from the payload's hidden input if present)."""
        model = _unwrap_model(ann)
        if isinstance(node, dict) and model is not None:
            for name, fi in model.model_fields.items():
                if name in node:
                    self._assign_keys(node[name], path + (name,), fi.annotation)
        elif isinstance(node, list) and get_origin(ann) is list:
            item_ann = get_args(ann)[0]
            for i, row in enumerate(node):
                if isinstance(row, dict):
                    if KEY not in row:
                        row[KEY] = new_key()
                    self._assign_keys(row, path + (i,), item_ann)

    # ---------------------------------------------------------------- union shelf
    def _apply_shelf(self, node, path, ann):
        """For discriminated unions: remember the params of each variant; when the tag switches back,
        restore what the user had typed for that variant (the client only sends the rendered variant)."""
        model = _unwrap_model(ann)
        if isinstance(node, dict) and model is not None:
            for name, fi in model.model_fields.items():
                sub_ann = fi.annotation
                if name in node and _is_discriminated(sub_ann, fi):
                    tag_field = fi.discriminator if isinstance(fi.discriminator, str) else None
                    sub = node[name]
                    if isinstance(sub, dict) and tag_field and tag_field in sub:
                        tag = sub[tag_field]
                        shelf = self.shelf.setdefault(path + (name,), {})
                        merged = {**shelf.get(tag, {}), **sub}
                        shelf[tag] = merged
                        node[name] = merged
                elif name in node:
                    self._apply_shelf(node[name], path + (name,), sub_ann)
        elif isinstance(node, list) and get_origin(ann) is list:
            for i, row in enumerate(node):
                self._apply_shelf(row, path + (i,), get_args(ann)[0])
        return node

    def __getitem__(self, name):
        return Field(self, (name,))


def _is_discriminated(ann, fi) -> bool:
    return fi.discriminator is not None and get_origin(ann) in (Union, types.UnionType)


def _strip_meta(node):
    if isinstance(node, dict):
        return {k: _strip_meta(v) for k, v in node.items() if k not in (KEY, INTENT)}
    if isinstance(node, list):
        return [_strip_meta(v) for v in node]
    return node


class Field(_Field):
    @property
    def key(self):
        v = self.value
        return v.get(KEY) if isinstance(v, dict) else None

    @property
    def id(self) -> str:
        """DOM ids use row keys instead of indices so reorders don't re-id inputs."""
        parts = [self.form.as_]
        node = self.form.params
        for seg in self.path:
            try:
                node = node[seg]
            except (KeyError, IndexError, TypeError):
                node = None
            if isinstance(seg, int) and isinstance(node, dict) and KEY in node:
                parts.append(node[KEY])
            else:
                parts.append(str(seg))
        return "_".join(parts)

    def __getitem__(self, key):
        if isinstance(key, str) and key.isdigit():
            key = int(key)
        return Field(self.form, self.path + (key,))

    def items(self):
        v = self.value
        return [self[i] for i in range(len(v))] if isinstance(v, list) else []

    # -- markup helpers the widgets would emit --
    def intent_button(self, op: str, label: str) -> str:
        return (f'<button type="button" name="{self.form.as_}{"".join(f"[{p}]" for p in self.path)}[{INTENT}]" '
                f'value="{op}" phx-click=\'[["dispatch",{{"event":"change"}}]]\'>{label}</button>')

    def key_input(self) -> str:
        return f'<input type="hidden" name="{self.name}[{KEY}]" value="{self.key}">'
