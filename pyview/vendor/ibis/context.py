import datetime
from . import errors


# User-configurable functions and variables available in all contexts.
builtins = {
    'now': datetime.datetime.now,
    'range': range,
}


# A wrapper around a stack of dictionaries.
class DataStack:

    def __init__(self):
       self.stack = []

    def __getitem__(self, key):
        for d in reversed(self.stack):
            if key in d:
                return d[key]
        raise KeyError(key)


# A Context object is a wrapper around the user's input data. Its `.resolve()` method contains
# the lookup-logic for resolving dotted variable names.
class Context:

    def __init__(self, data_dict, strict_mode):
        # Stack of data dictionaries for the .resolve() method.
        self.data = DataStack()

        # Standard builtins.
        self.data.stack.append({
            'context': self,
            'is_defined': self.is_defined,
        })

        # User-configurable builtins.
        self.data.stack.append(builtins)

        # Instance-specific data.
        self.data.stack.append(data_dict)

        # Nodes can store state information here to avoid threading issues.
        self.stash = {}

        # Chain of ancestor templates.
        self.templates = []

        # In strict mode undefined variables raise an UndefinedVariable exception.
        self.strict_mode = strict_mode

    def __setitem__(self, key, value):
        self.data.stack[-1][key] = value

    def __getitem__(self, key):
        return self.data[key]

    def push(self, data=None):
        self.data.stack.append(data or {})

    def pop(self):
        self.data.stack.pop()

    def get(self, key, default=None):
        for d in reversed(self.data.stack):
            if key in d:
                return d[key]
        return default

    def update(self, data_dict):
        self.data.stack[-1].update(data_dict)

    def resolve(self, varstring, token):
        words = []
        result = self.data
        for word in varstring.split('.'):
            words.append(word)
            if hasattr(result, word):
                result = getattr(result, word)
            else:
                try:
                    result = result[word]
                except:
                    try:
                        result = result[int(word)]
                    except:
                        if self.strict_mode:
                            msg = f"Cannot resolve the variable '{'.'.join(words)}' in template "
                            msg += f"'{token.template_id}', line {token.line_number}."
                            raise errors.UndefinedVariable(msg, token) from None
                        return Undefined()
        return result

    def is_defined(self, varstring):
        current = self.data
        for word in varstring.split('.'):
            if hasattr(current, word):
                current = getattr(current, word)
            else:
                try:
                    current = current[word]
                except:
                    try:
                        current = current[int(word)]
                    except:
                        return False
        return True


# Null type returned when a context lookup fails.
class Undefined:

    def __str__(self):
        return ''

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __contains__(self, key):
        return False

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

