from pyview.template.context_processor import context_processor


@context_processor
def add_root_path(meta) -> dict:
    return {"root_path": meta.root_path}
