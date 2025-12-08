# File Uploads

Need to let users upload files? You're in the right place. PyView gives you a complete upload system with progress tracking, validation, drag-and-drop, and image previews—all wired up to work seamlessly with LiveView's real-time updates.

You have two options for where files end up:

| | Direct Uploads | External Uploads |
|----------|---------------|------------------|
| **Where files go** | Your server | Cloud storage (S3, GCS, Azure) |
| **Best for** | Small files (<10MB) | Large files, high traffic |
| **Server load** | Higher (data flows through server) | Lower (browser → cloud directly) |
| **Can pre-process?** | Yes - transform, scan, validate | No - files go straight to cloud |
| **Setup** | Simpler | Requires cloud provider config |

## Where to Start

**[Direct Uploads](direct.md)** — Start here. Upload files to your server with progress bars, validation, and drag-and-drop. This covers the most common use cases.

**[External Uploads](external.md)** — For large files or when you need to reduce server load. Files go directly from the browser to S3 (or similar) using presigned URLs.

Both approaches share the same template helpers and progress tracking—the difference is just where the bytes end up.
