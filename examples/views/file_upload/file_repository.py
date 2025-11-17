import base64
import collections
from io import BytesIO

from PIL import Image


class FileEntry:
    file_name: str
    file_bytes: bytes
    content_type: str

    def __init__(self, file_name, file_path, content_type):
        self.file_name = file_name
        self.content_type = content_type
        self.file_bytes = create_thumbnail_bytes(file_path)

    @property
    def base64(self):
        return base64.b64encode(self.file_bytes).decode("utf-8")

    @property
    def inline_image(self):
        return f"data:{self.content_type};base64,{self.base64}"


class FileRepository:
    """
    A simple repository to store file entries thumbnails as base64 strings for demo purposes.
    """
    def __init__(self):
        self.all_files = collections.deque(maxlen=10)

    def add_file(self, file_name, file_path, content_type):
        file_entry = FileEntry(file_name, file_path, content_type)
        self.all_files.append(file_entry)
        return file_entry

    def get_all_files(self):
        return self.all_files


def create_thumbnail_bytes(input_image_path, size=(128, 128)):
    with Image.open(input_image_path) as img:
        img.thumbnail(size)
        byte_io = BytesIO()
        img.save(byte_io, "JPEG")
        byte_io.seek(0)
        return byte_io.getvalue()
