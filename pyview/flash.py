from pyview.template.context_processor import context_processor


@context_processor
def add_flash(meta) -> dict:
    socket = meta.socket
    if socket is not None:
        return {"flash": socket.flash}
    return {"flash": {}}
