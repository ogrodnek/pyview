# External Uploads

External uploads let files go directly from the browser to cloud storage (S3, GCS, Azure) without passing through your server. This is the right choice for large files, high-traffic scenarios, or when you're already storing files in the cloud.

The pattern is the same across cloud providers: your server generates a temporary presigned URL, and the browser uploads directly using that URL. Your server never touches the file bytes—just the metadata.

> **Note:** The examples here use AWS S3, but the concepts apply to any cloud provider that supports presigned URLs.

## How It Works

1. User selects files in the browser
2. Your server generates presigned upload URLs (with size limits, expiration, etc.)
3. Browser uploads directly to cloud storage
4. Progress is reported back to your LiveView
5. Your server records the file metadata once upload completes

No file data flows through your server—just the orchestration.

## Basic Setup

### 1. Create a Presign Function

This function runs on your server for each file. It generates a temporary URL that lets the browser upload directly to S3:

```python
import boto3
from pyview.uploads import UploadEntry, ExternalUploadMeta

async def presign_s3_upload(entry: UploadEntry, socket) -> ExternalUploadMeta:
    """Generate a presigned POST URL for direct S3 upload."""
    s3 = boto3.client('s3')

    # Put files in a user-specific path
    key = f"uploads/{socket.context.user_id}/{entry.uuid}/{entry.name}"

    presigned = s3.generate_presigned_post(
        Bucket="my-bucket",
        Key=key,
        Fields={"Content-Type": entry.type},
        Conditions=[
            {"Content-Type": entry.type},
            ["content-length-range", 0, entry.size]  # Enforce size limit
        ],
        ExpiresIn=3600  # URL valid for 1 hour
    )

    return ExternalUploadMeta(
        uploader="S3",  # Must match client-side uploader name
        url=presigned['url'],
        fields=presigned['fields'],
        key=key,  # Store for later reference
    )
```

**What's happening here:** You're asking S3 for a temporary, limited-permission URL. The browser can use this URL to upload *one specific file* with *specific constraints*. Your AWS credentials never leave your server.

### 2. Configure the Upload

Pass your presign function to `allow_upload()`:

```python
from dataclasses import dataclass
from pyview import LiveView, LiveViewSocket
from pyview.uploads import UploadConfig, UploadConstraints

@dataclass
class MyContext:
    upload_config: UploadConfig
    user_id: str

class UploadView(LiveView[MyContext]):
    async def mount(self, socket: LiveViewSocket[MyContext], session):
        config = socket.allow_upload(
            "files",
            constraints=UploadConstraints(
                max_file_size=100 * 1024 * 1024,  # 100MB
                max_files=5,
                accept=["image/*", "video/*"]
            ),
            external=presign_s3_upload  # This enables external uploads
        )

        socket.context = MyContext(
            upload_config=config,
            user_id=session.get("user_id")
        )
```

### 3. Handle Completion

When uploads finish, the files are already on S3. You just need to record the metadata:

```python
async def handle_event(self, event, payload, socket):
    if event == "save":
        for entry in socket.context.upload_config.entries:
            if entry.done and entry.meta:
                # File is already on S3 - just save the reference
                await save_to_database(
                    user_id=socket.context.user_id,
                    filename=entry.name,
                    size=entry.size,
                    s3_key=entry.meta.key
                )

        # Clear processed entries
        socket.context.upload_config.entries_by_ref.clear()
```

### 4. Include the Client-Side Uploader

Add the provided pyview s3 uploaders script to your HTML:

```html
<script defer src="/static/assets/uploaders.js"></script>
```

This provides `S3` and `S3Multipart` uploaders that work with the presigned URLs.

---

## Handling Upload Results

For more control over success/failure handling, use the `entry_complete` callback:

```python
from pyview.uploads import UploadResult, UploadSuccess, UploadSuccessWithData, UploadFailure

async def on_upload_complete(entry, result: UploadResult, socket):
    match result:
        case UploadFailure(error):
            socket.context.error = f"Upload failed: {error}"

        case UploadSuccess():
            # Simple upload completed
            await save_to_database(entry.name, entry.meta.key)

        case UploadSuccessWithData(data):
            # Multipart upload completed - data contains parts info
            await finalize_multipart(entry, data)

# Configure with the callback
config = socket.allow_upload(
    "files",
    constraints=UploadConstraints(...),
    external=presign_s3_upload,
    entry_complete=on_upload_complete
)
```

---

## S3 Configuration

### CORS

Your S3 bucket needs CORS configured to allow browser uploads. This is the most common source of "it's not working" issues:

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["POST", "PUT"],
        "AllowedOrigins": [
            "http://localhost:8000",
            "https://yourdomain.com"
        ],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3000
    }
]
```

Apply it:

```bash
aws s3api put-bucket-cors --bucket your-bucket --cors-configuration file://cors.json
```

**Tip:** CORS errors can be frustrating to debug. If uploads aren't working, check the browser console first—CORS issues show up clearly there.

### IAM Permissions

Your AWS credentials need at minimum:
- `s3:PutObject` — Required for presigned POST generation

### Cleaning Up Incomplete Uploads

If users cancel mid-upload or lose connectivity, incomplete multipart uploads sit in S3 and *still cost you money*. Set up a lifecycle rule to clean them up automatically:

```json
{
  "Rules": [{
    "Id": "CleanupIncompleteUploads",
    "Status": "Enabled",
    "Filter": { "Prefix": "uploads/" },
    "AbortIncompleteMultipartUpload": {
      "DaysAfterInitiation": 7
    }
  }]
}
```

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket \
  --lifecycle-configuration file://lifecycle.json
```

---

## Multipart Uploads

For very large files (>5GB), use the `S3Multipart` uploader. It uploads in chunks, which is more reliable for large files and allows resuming interrupted uploads.

Set `uploader="S3Multipart"` in your presign function and include the upload ID in the response.

---

## Security Checklist

- **Short URL expiration** — Presigned URLs should expire in 1-2 hours max
- **User-specific paths** — Include user ID in the S3 key to prevent overwrites
- **Size limits** — Enforce in both `UploadConstraints` and presigned conditions
- **Content-Type validation** — Validate in presigned conditions
- **Private buckets** — Don't make your upload bucket public

---

## Troubleshooting

### "Access to XMLHttpRequest blocked by CORS policy"

CORS isn't configured on your S3 bucket. See the CORS section above. Double-check that `AllowedOrigins` includes your exact domain (including port for local dev).

### "Error calling presign function for entry"

Your presign function is failing. Check:
- AWS credentials are configured
- Bucket exists and you have access
- `boto3` is installed
- Look for exceptions in your server logs

### Uploads don't start

Check the browser console. Common issues:
- `uploaders.js` not included
- `uploader` field in `ExternalUploadMeta` doesn't match ("S3" vs "s3")
- JavaScript errors preventing initialization

### File not appearing in S3

- Check browser network tab for the upload request status
- Verify the presigned POST includes the correct bucket and key
- Confirm your credentials have `s3:PutObject` permission

---

For uploads that go through your server, see [Direct Uploads](direct.md).
