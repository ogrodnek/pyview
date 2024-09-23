from pyview.meta import PyViewMeta

context_processors = []


def context_processor(func):
    context_processors.append(func)
    return func


def apply_context_processors(meta: PyViewMeta):
    context = {}

    for processor in context_processors:
        context.update(processor(meta))

    return context
