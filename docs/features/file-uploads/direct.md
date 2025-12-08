# Direct Uploads

Direct uploads send files through your server, giving you full control to validate, transform, or scan files before storing them. This is the right choice for many applications— it's simple to set up and covers common use cases like profile photos, documents, and small media files.

## Quick Start

Here's a minimal working upload in three parts: configuration, template, and event handling.

### 1. Configure the Upload

In your LiveView's `mount()`, call `allow_upload()` to define what files you'll accept:

```python
from pyview import LiveView, LiveViewSocket
from pyview.uploads import UploadConfig, UploadConstraints
from dataclasses import dataclass

@dataclass
class UploadContext:
    upload_config: UploadConfig
    uploaded_files: list = None

    def __post_init__(self):
        if self.uploaded_files is None:
            self.uploaded_files = []

class FileUploadView(LiveView[UploadContext]):
    async def mount(self, socket: LiveViewSocket[UploadContext], session):
        config = socket.allow_upload(
            "documents",
            constraints=UploadConstraints(
                max_file_size=5 * 1024 * 1024,  # 5MB
                max_files=3,
                accept=[".pdf", ".doc", ".docx"]
            )
        )
        socket.context = UploadContext(upload_config=config)
```

### 2. Add the Template

The `live_file_input` filter creates the file input, and `phx-drop-target` enables drag-and-drop:

```html
<form phx-submit="save" phx-change="validate">
    <div phx-drop-target="{{upload_config.ref}}" class="upload-zone">
        <p>Drop files here or click to select</p>
        {{ upload_config | live_file_input }}
    </div>

    <!-- Show files waiting to upload -->
    {% for entry in upload_config.entries %}
        <div class="upload-entry">
            <span>{{ entry.name }}</span>
            <div class="progress" style="width: {{ entry.progress }}%"></div>
            <button type="button" phx-click="cancel" phx-value-ref="{{ entry.ref }}">×</button>
        </div>
    {% endfor %}

    <!-- Show any errors -->
    {% for error in upload_config.errors %}
        <div class="error">{{ error.message }}</div>
    {% endfor %}

    <button type="submit">Upload</button>
</form>
```

### 3. Handle the Upload

When the form submits, use `consume_uploads()` to access the uploaded files:

```python
async def handle_event(self, event, payload, socket: LiveViewSocket[UploadContext]):
    if event == "save":
        with socket.context.upload_config.consume_uploads() as uploads:
            for upload in uploads:
                # upload.file is a temp file, upload.entry has metadata
                saved_path = await self.save_file(upload.file, upload.entry.name)
                socket.context.uploaded_files.append({
                    "name": upload.entry.name,
                    "path": saved_path
                })

    elif event == "cancel":
        socket.context.upload_config.cancel_entry(payload["ref"])

async def save_file(self, temp_file, filename: str) -> str:
    import os, shutil, uuid
    os.makedirs("uploads", exist_ok=True)
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(filename)[1]
    path = f"uploads/{file_id}{ext}"
    shutil.copy2(temp_file.name, path)
    return path
```

That's it! You now have working file uploads with progress tracking and drag-and-drop.

---

## Going Further

Once basic uploads are working, you might want to add auto-upload, image previews, or custom validation. Each section below builds on the basics.

### Auto-Upload Mode

By default, files wait until the form is submitted. With `auto_upload=True`, files start uploading immediately when selected—great for photo galleries or when you want instant feedback:

```python
config = socket.allow_upload(
    "photos",
    constraints=UploadConstraints(
        max_file_size=10 * 1024 * 1024,
        max_files=10,
        accept=[".jpg", ".jpeg", ".png"]
    ),
    auto_upload=True,
    progress=self.handle_progress  # Called on each progress update
)
```

The `progress` callback fires as uploads progress. Check `entry.done` to know when a file finishes:

```python
async def handle_progress(self, entry, socket):
    if entry.done:
        # Process this file immediately instead of waiting for form submit
        with socket.context.upload_config.consume_upload_entry(entry.ref) as upload:
            if upload:
                path = await self.save_file(upload.file, upload.entry.name)
                socket.context.uploaded_files.append({"name": entry.name, "path": path})
```

### Image Previews

For image uploads, you can show thumbnails before the upload completes using the `upload_preview_tag` filter:

```html
{% for entry in upload_config.entries %}
    <div class="preview-item">
        {{ entry | upload_preview_tag }}
        <span>{{ entry.name }}</span>
    </div>
{% endfor %}
```

This generates a client-side preview—no server round-trip needed.

---

## Constraints and Validation

### Built-in Constraints

`UploadConstraints` handles the common cases:

```python
constraints = UploadConstraints(
    max_file_size=10 * 1024 * 1024,  # 10MB per file
    max_files=5,                      # Max 5 files at once
    accept=[".jpg", ".png", ".pdf"],  # Allowed extensions
    chunk_size=64 * 1024              # 64KB chunks (for large files)
)
```

When constraints are violated, errors appear in `upload_config.errors` automatically.

## Error Handling

Errors can come from constraint violations or your own code. Here's how to handle both:

```python
async def handle_progress(self, entry, socket):
    if entry.done:
        try:
            with socket.context.upload_config.consume_upload_entry(entry.ref) as upload:
                if upload:
                    await self.process_file(upload.file, upload.entry)
        except Exception as e:
            # Set an error message the user can see
            socket.context.error_message = f"Failed to process {entry.name}"
            import logging
            logging.exception(f"Upload error: {entry.name}")
```

In your template, display errors from both the upload config and your own handling:

```html
{% for error in upload_config.errors %}
    <div class="error">{{ error.message }}</div>
{% endfor %}

{% if error_message %}
    <div class="error">{{ error_message }}</div>
{% endif %}
```

---

## Security Best Practices

PyView handles temp file cleanup automatically, but you should still be careful with user-uploaded files.

### Store Files Safely

Never use the original filename directly—generate a unique name:

```python
import os, uuid, shutil
from pathlib import Path

async def save_securely(temp_file, original_name: str) -> dict:
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    # Generate safe filename
    file_id = str(uuid.uuid4())
    ext = Path(original_name).suffix.lower()

    # Validate extension
    allowed = {'.jpg', '.jpeg', '.png', '.pdf'}
    if ext not in allowed:
        raise ValueError(f"Extension {ext} not allowed")

    safe_path = upload_dir / f"{file_id}{ext}"
    shutil.copy2(temp_file.name, safe_path)

    return {"id": file_id, "path": str(safe_path), "original_name": original_name}
```

## Complete Example

Here's a focused photo upload with auto-upload and thumbnails:

```python
from datetime import datetime
from pyview import LiveView, LiveViewSocket, is_connected
from pyview.uploads import UploadConfig, UploadConstraints
from dataclasses import dataclass, field
import os, uuid, shutil, base64
from PIL import Image
from io import BytesIO

@dataclass
class PhotoContext:
    upload_config: UploadConfig
    photos: list = field(default_factory=list)
    error: str = ""

class PhotoUploadView(LiveView[PhotoContext]):
    async def mount(self, socket: LiveViewSocket[PhotoContext], session):
        config = socket.allow_upload(
            "photos",
            constraints=UploadConstraints(
                max_file_size=10 * 1024 * 1024,
                max_files=10,
                accept=[".jpg", ".jpeg", ".png"]
            ),
            auto_upload=True,
            progress=self.on_progress
        )
        socket.context = PhotoContext(upload_config=config)

    async def on_progress(self, entry, socket):
        if entry.done and entry.valid:
            try:
                with socket.context.upload_config.consume_upload_entry(entry.ref) as upload:
                    if upload:
                        photo = await self.save_photo(upload.file, upload.entry)
                        socket.context.photos.append(photo)
                        socket.context.error = ""
            except Exception as e:
                socket.context.error = f"Failed: {entry.name}"

    async def save_photo(self, temp_file, entry) -> dict:
        photo_id = str(uuid.uuid4())
        os.makedirs("uploads", exist_ok=True)

        ext = os.path.splitext(entry.name)[1].lower()
        path = f"uploads/{photo_id}{ext}"
        shutil.copy2(temp_file.name, path)

        # Create thumbnail
        with Image.open(temp_file.name) as img:
            img.thumbnail((150, 150))
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=80)
            thumb = base64.b64encode(buf.getvalue()).decode()

        return {"id": photo_id, "name": entry.name, "path": path, "thumb": thumb}

    async def handle_event(self, event, payload, socket):
        if event == "cancel":
            socket.context.upload_config.cancel_entry(payload["ref"])
```

For large files or when you want to reduce server load, see [External Uploads](external.md).
