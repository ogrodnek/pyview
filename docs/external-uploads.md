# External Uploads

External uploads allow files to be uploaded directly from the browser to cloud storage (Amazon S3, Google Cloud Storage, Azure Blob Storage, etc.) without the data passing through your server. This provides better scalability, reduces server bandwidth, and improves upload performance for large files.

## Overview

### How It Works

1. **Client selects files** - User chooses files in the browser
2. **Server generates presigned URLs** - Your server creates temporary upload URLs with appropriate permissions
3. **Client uploads directly** - Browser uploads files directly to cloud storage using the presigned URL
4. **Progress tracking** - Client reports progress back to the LiveView server
5. **Completion** - Server is notified when uploads complete

## Basic Setup

### 1. Define Your Context

```python
from dataclasses import dataclass
from pyview import LiveView, LiveViewSocket
from pyview.uploads import UploadConfig, UploadConstraints, UploadEntry, ExternalUploadMeta

@dataclass
class MyContext:
    upload_config: UploadConfig
    user_id: str
    s3_bucket: str
    s3_region: str
```

### 2. Create Presign Function

The presign function receives an `UploadEntry` and your context, and returns `ExternalUploadMeta`:

```python
import boto3

async def presign_s3_upload(entry: UploadEntry, context: MyContext) -> ExternalUploadMeta:
    """Generate presigned S3 POST data for direct upload."""
    s3_client = boto3.client('s3')

    # Generate unique key for this upload
    key = f"uploads/{context.user_id}/{entry.uuid}/{entry.name}"

    # Generate presigned POST
    presigned_post = s3_client.generate_presigned_post(
        Bucket="my-bucket", # important: put your bucket name here
        Key=key,
        Fields={"Content-Type": entry.type},
        Conditions=[
            {"Content-Type": entry.type},
            ["content-length-range", 0, entry.size]
        ],
        ExpiresIn=3600  # URL valid for 1 hour
    )

    return ExternalUploadMeta(
        uploader="S3",
        url=presigned_post['url'],
        fields=presigned_post['fields'],
        key=key,  # Optional: store for later reference
    )
```

### 3. Configure Upload in LiveView

```python
class MyLiveView(LiveView[MyContext]):
    async def mount(self, socket: LiveViewSocket[MyContext], session):
        config = socket.allow_upload(
            "photos",
            constraints=UploadConstraints(
                max_file_size=10 * 1024 * 1024,  # 10MB
                max_files=5,
                accept=["image/*"],
            ),
            external=presign_s3_upload,  # Enable external uploads
        )

        socket.context = MyContext(
            upload_config=config,
            user_id=session.get("user_id")
        )
```

### 4. Handle Upload Completion

For simple uploads, handle the files in your event handler:

```python
    async def handle_event(self, event, payload, socket: LiveViewSocket[MyContext]):
        if event == "save":
            # Files are already on S3!
            for entry in socket.context.upload_config.entries:
                if entry.done and entry.meta:
                    # Access S3 metadata from entry.meta
                    s3_key = entry.meta.key
                    s3_url = entry.meta.url

                    # Save metadata to database
                    await save_file_metadata(
                        user_id=socket.context.user_id,
                        filename=entry.name,
                        size=entry.size,
                        s3_key=s3_key,
                        s3_url=f"{s3_url}/{s3_key}"
                    )

            # Clear entries after saving
            socket.context.upload_config.entries_by_ref.clear()
```

For multipart uploads or when you need to handle errors/completion automatically, use the `entry_complete` callback with pattern matching:

```python
from pyview.uploads import UploadResult, UploadSuccess, UploadSuccessWithData, UploadFailure

async def handle_upload_completion(
    entry: UploadEntry,
    result: UploadResult,
    socket: LiveViewSocket[MyContext]
):
    """Handle upload completion or failure using pattern matching (Python 3.10+)."""
    match result:
        case UploadFailure(error):
            # Upload failed - clean up, log error, notify user
            logger.error(f"Upload failed for {entry.name}: {error}")
            # For multipart: abort S3 multipart upload to prevent storage charges

        case UploadSuccessWithData(data):
            # Multipart upload completed - finalize with S3
            # data contains: {complete: true, upload_id: "...", parts: [...]}
            await complete_multipart_upload(entry, data, socket)

        case UploadSuccess():
            # Simple upload completed
            logger.info(f"Upload completed: {entry.name}")

# Configure with callback
config = socket.allow_upload(
    "files",
    constraints=UploadConstraints(...),
    external=presign_s3_upload,
    entry_complete=handle_upload_completion  # Called on success or failure
)
```

## Accessing External Upload Metadata

After an external upload completes, the metadata you returned from your presign function is available via `entry.meta`:

```python
for entry in config.entries:
    if entry.done and entry.meta:
        # Access any field you included in ExternalUploadMeta
        s3_key = entry.meta.key
        s3_url = entry.meta.url
        bucket = entry.meta.bucket  # If you added this field

        # Use metadata to save to database, generate thumbnails, etc.
        await save_to_database(s3_key=s3_key, url=s3_url)
```

**Key Points:**
- `entry.meta` is `None` for internal uploads (only set for external)
- `entry.meta` contains the `ExternalUploadMeta` object you returned from your presign function
- All custom fields you added (like `key`, `bucket`, etc.) are accessible
- Metadata is automatically cleaned up when entries are consumed or cancelled

## ExternalUploadMeta

The `ExternalUploadMeta` model defines what you return from your presign function:

```python
class ExternalUploadMeta(BaseModel):
    uploader: str  # Required: Name of JS uploader ("S3", "GCS", "Azure")
    # ... any other fields your uploader needs
```

The `uploader` field is required and must match a client-side JavaScript uploader name. You can add any provider-specific fields using Pydantic's `extra="allow"` configuration:

```python
ExternalUploadMeta(
    uploader="S3",
    url="https://bucket.s3.amazonaws.com",
    fields={"key": "...", "policy": "...", "signature": "..."},
    # Add custom fields that will be accessible later via entry.meta
    key="uploads/user123/file.jpg",
    bucket="my-bucket",
    region="us-east-1",
)
```

## Client-Side Configuration

PyView provides S3 and S3Multipart uploaders in a separate JavaScript file. Include it in your HTML if you're using external uploads:

```html
<script defer type="text/javascript" src="/static/assets/uploaders.js"></script>
```

This provides:
- `S3` - Simple POST upload using presigned POST URLs (files up to ~5GB)
- `S3Multipart` - Multipart upload for large files (>5GB, see [Multipart Upload Example](../examples/views/multipart_upload/))

You can customize these uploaders or add your own:

### Using the Provided Uploaders

Once you include `uploaders.js`, the S3 and S3Multipart uploaders are available. They work with standard S3 presigned URLs and require no additional configuration.



## Cloud Provider Setup

### Amazon S3 CORS Configuration

Your S3 bucket needs CORS configuration to allow uploads from your domain:

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

**To set via AWS CLI:**

```bash
aws s3api put-bucket-cors --bucket your-bucket --cors-configuration file://cors.json
```

### Bucket Permissions

Ensure your AWS credentials have permission to:
- `s3:PutObject` - Required for generating presigned POST
- `s3:GetObject` - Optional, if you want to retrieve files later

### S3 Lifecycle Policy for Multipart Uploads

**Important for Multipart Uploads**: Incomplete multipart uploads continue to occupy S3 storage and **incur storage charges** indefinitely until explicitly aborted or deleted. This can happen when users cancel uploads, experience network errors, or close their browser mid-upload.

**AWS Best Practice**: Configure S3 bucket lifecycle rules to automatically delete incomplete multipart uploads after a specified period.

#### Lifecycle Policy Example

Delete incomplete uploads after 7 days:

```json
{
  "Rules": [
    {
      "Id": "DeleteIncompleteMultipartUploads",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "uploads/"
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
```

#### Apply via AWS CLI

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket-name \
  --lifecycle-configuration file://lifecycle-policy.json
```

#### Apply via AWS Console

1. Go to S3 → Your Bucket → **Management** → **Lifecycle rules**
2. Click **Create lifecycle rule**
3. **Rule name**: "Delete incomplete multipart uploads"
4. **Rule scope**: Choose "Limit the scope using one or more filters" → Prefix: `uploads/`
5. **Lifecycle rule actions**: Check "Delete expired object delete markers or incomplete multipart uploads"
6. **Days after initiation**: `7` days
7. Click **Create rule**

**Cost Impact**: Without this policy, incomplete uploads accumulate storage costs. A 1GB incomplete upload costs the same as a completed 1GB file but serves no purpose.

**Note**: This lifecycle policy is especially important if you're using the S3Multipart uploader for large files, but it's good practice to enable it for all S3 buckets that handle uploads.

### Security Considerations

1. **Short expiration times** - Presigned URLs should expire quickly (1-2 hours)
2. **User-specific paths** - Include user ID in the S3 key to prevent overwrites
3. **Size limits** - Enforce `max_file_size` in both upload config and presigned policy
4. **Content-Type restrictions** - Validate file types in presigned conditions
5. **Don't expose credentials** - Never send AWS keys to the client
6. **Bucket policies** - Set appropriate bucket policies to prevent public access

## Error Handling

### Client-Side Errors

The JavaScript uploader should report errors back to LiveView:

```javascript
xhr.onload = () => {
  if (xhr.status === 204) {
    entry.progress(100);
  } else {
    entry.error(`Upload failed with status ${xhr.status}`);
  }
};

xhr.onerror = () => entry.error("Network error during upload");
```

### Server-Side Validation

Errors during presigning or constraint validation are automatically handled:

```python
# Constraint violations (file too large, too many files)
# are automatically caught and reported to the client

# Errors in your presign function should be handled:
async def presign_s3(entry: UploadEntry, context) -> ExternalUploadMeta:
    try:
        # Generate presigned URL
        ...
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise  # Will be caught and reported as "presign_error"
```

### Progress Tracking

Upload progress is automatically tracked and reported. You can add a progress callback:

```python
async def track_progress(entry: UploadEntry, socket):
    logger.info(f"Upload progress for {entry.name}: {entry.progress}%")

socket.allow_upload(
    "files",
    constraints=UploadConstraints(...),
    external=presign_s3,
    progress=track_progress
)
```

## Internal vs External Uploads

### When to Use External Uploads

✅ Use external uploads when:
- Uploading large files (>10MB)
- Expecting many concurrent uploads
- Files will be stored in cloud storage anyway
- You want to reduce server load

### When to Use Internal Uploads

✅ Use internal uploads when:
- Uploading small files (<1MB)
- Need to process/transform files before storage
- Storing files on your server
- Simple use case without cloud storage
- Need to virus scan before accepting





## Troubleshooting

### CORS Errors

**Error:** `Access to XMLHttpRequest blocked by CORS policy`

**Solution:** Configure CORS on your S3 bucket (see Cloud Provider Setup section)

**Check:**
- `AllowedOrigins` includes your domain
- `AllowedMethods` includes `POST`
- `AllowedHeaders` includes `*` or the specific headers you're using

### Presigning Errors

**Error:** `Error calling presign function for entry`

**Solution:** Check your presign function:
- AWS credentials are configured correctly
- Bucket exists and you have access
- boto3 is installed (`pip install boto3`)
- Exception handling in your presign function

### Uploads Not Starting

**Check:**
1. Is `uploaders.js` included in your HTML? `<script src="/static/assets/uploaders.js"></script>`
2. Does `entry.meta.uploader` match a defined uploader name ("S3" or "S3Multipart")?
3. Check browser console for JavaScript errors
4. Verify `ExternalUploadMeta` includes required `uploader` field

### File Not Appearing on S3

**Check:**
1. Presigned POST includes correct `bucket` and `key`
2. Browser network tab shows successful 204 response
3. AWS credentials have `s3:PutObject` permission
4. Bucket policy doesn't block the upload

## Additional Resources

- [Phoenix LiveView external uploads docs](https://hexdocs.pm/phoenix_live_view/uploads-external.html)
- [AWS S3 Presigned POST documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)
