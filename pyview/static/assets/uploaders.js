/**
 * PyView External S3 Uploaders
 *
 * Client-side uploaders for external S3 uploads.
 *
 * Available uploaders:
 * - S3: Simple POST upload to S3 using presigned POST URLs
 * - S3Multipart: Multipart upload for large files (>5GB)
 */

window.Uploaders = window.Uploaders || {};

// S3 Simple POST uploader
// Uses presigned POST URLs for direct upload to S3
// Works for files up to ~5GB
if (!window.Uploaders.S3) {
  window.Uploaders.S3 = function (entries, onViewError) {
    entries.forEach((entry) => {
      let formData = new FormData();
      let { url, fields } = entry.meta;

      // Add all fields from presigned POST
      Object.entries(fields).forEach(([key, val]) =>
        formData.append(key, val)
      );
      formData.append("file", entry.file);

      let xhr = new XMLHttpRequest();
      onViewError(() => xhr.abort());

      xhr.onload = () => {
        if (xhr.status === 204 || xhr.status === 200) {
          entry.progress(100);
        } else {
          entry.error(`S3 upload failed with status ${xhr.status}`);
        }
      };
      xhr.onerror = () => entry.error("Network error during upload");

      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          let percent = Math.round((event.loaded / event.total) * 100);
          if (percent < 100) {
            entry.progress(percent);
          }
        }
      });

      xhr.open("POST", url, true);
      xhr.send(formData);
    });
  };
}

// S3 Multipart uploader for large files
// Uploads file in chunks with retry logic and concurrency control
//
// - Exponential backoff retry (max 3 attempts per part)
// - Concurrency limit (max 6 parallel uploads)
// - Automatic cleanup on fatal errors
//
// Based on AWS best practices:
// https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
//
// Server must:
// 1. Return metadata with: uploader="S3Multipart", upload_id, part_urls, chunk_size
// 2. Provide entry_complete callback to finalize the upload
if (!window.Uploaders.S3Multipart) {
  window.Uploaders.S3Multipart = function (entries, onViewError) {
    entries.forEach((entry) => {
      const { upload_id, part_urls, chunk_size, key } = entry.meta;
      const file = entry.file;
      const parts = []; // Store {PartNumber, ETag} for each uploaded part

      const MAX_RETRIES = 3;
      const MAX_CONCURRENT = 6;
      let uploadedParts = 0;
      let activeUploads = 0;
      let partIndex = 0;
      let hasError = false;
      const totalParts = part_urls.length;

      console.log(`[S3Multipart] Starting upload for ${entry.file.name}`);
      console.log(`[S3Multipart] Total parts: ${totalParts}, chunk size: ${chunk_size}`);
      console.log(`[S3Multipart] Max concurrent uploads: ${MAX_CONCURRENT}, max retries: ${MAX_RETRIES}`);

      // Add a custom method to send completion data directly
      // This bypasses entry.progress() which only handles numbers
      entry.complete = function(completionData) {
        console.log(`[S3Multipart] Calling entry.complete with:`, completionData);
        // Call pushFileProgress directly with the completion data
        entry.view.pushFileProgress(entry.fileEl, entry.ref, completionData);
      };

      // Upload a single part with retry logic
      const uploadPart = (index, retryCount = 0) => {
        if (hasError) return;  // Stop if we've hit a fatal error

        const partNumber = index + 1;
        const url = part_urls[index];
        const start = index * chunk_size;
        const end = Math.min(start + chunk_size, file.size);
        const chunk = file.slice(start, end);

        console.log(`[S3Multipart] Starting part ${partNumber}/${totalParts}, size: ${chunk.size} bytes, attempt ${retryCount + 1}`);

        const xhr = new XMLHttpRequest();
        onViewError(() => xhr.abort());

        // Track upload progress within this chunk
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            // Calculate overall progress: completed parts + current part's progress
            const completedBytes = uploadedParts * chunk_size;
            const currentPartBytes = event.loaded;
            const totalBytes = file.size;
            const overallPercent = Math.round(((completedBytes + currentPartBytes) / totalBytes) * 100);

            // Don't report 100% until all parts complete and we send completion data
            if (overallPercent < 100) {
              entry.progress(overallPercent);
            }
          }
        });

        xhr.onload = () => {
          activeUploads--;

          if (xhr.status === 200) {
            const etag = xhr.getResponseHeader('ETag');
            console.log(`[S3Multipart] Part ${partNumber} succeeded, ETag: ${etag}`);

            if (!etag) {
              console.error(`[S3Multipart] Part ${partNumber} missing ETag!`);
              entry.error(`Part ${partNumber} upload succeeded but no ETag returned`);
              hasError = true;
              return;
            }

            // Store the part with its ETag
            parts.push({
              PartNumber: partNumber,
              ETag: etag.replace(/"/g, '')
            });
            uploadedParts++;

            // Update progress
            const progressPercent = Math.round((uploadedParts / totalParts) * 100);
            console.log(`[S3Multipart] Progress: ${uploadedParts}/${totalParts} parts (${progressPercent}%)`);

            if (uploadedParts < totalParts) {
              entry.progress(progressPercent < 100 ? progressPercent : 99);
              uploadNextPart();  // Start next part
            } else {
              // All parts complete!
              const completionData = {
                complete: true,
                upload_id: upload_id,
                key: key,
                parts: parts.sort((a, b) => a.PartNumber - b.PartNumber)
              };
              console.log(`[S3Multipart] All parts complete! Sending completion data`);
              entry.complete(completionData);
            }
          } else {
            // Upload failed - retry with exponential backoff
            console.error(`[S3Multipart] Part ${partNumber} failed with status ${xhr.status}, attempt ${retryCount + 1}`);

            if (retryCount < MAX_RETRIES) {
              // Exponential backoff: 1s, 2s, 4s, max 10s
              const delay = Math.min(1000 * (2 ** retryCount), 10000);
              console.log(`[S3Multipart] Retrying part ${partNumber} in ${delay}ms...`);

              setTimeout(() => {
                uploadPart(index, retryCount + 1);
              }, delay);
            } else {
              // Max retries exceeded - fatal error
              console.error(`[S3Multipart] Part ${partNumber} failed after ${MAX_RETRIES} retries, aborting upload`);
              entry.error(`Part ${partNumber} failed after ${MAX_RETRIES} attempts. Upload aborted.`);
              hasError = true;
            }
          }
        };

        xhr.onerror = () => {
          activeUploads--;
          console.error(`[S3Multipart] Network error on part ${partNumber}, attempt ${retryCount + 1}`);

          if (retryCount < MAX_RETRIES) {
            const delay = Math.min(1000 * (2 ** retryCount), 10000);
            console.log(`[S3Multipart] Retrying part ${partNumber} after network error in ${delay}ms...`);

            setTimeout(() => {
              uploadPart(index, retryCount + 1);
            }, delay);
          } else {
            console.error(`[S3Multipart] Part ${partNumber} network error after ${MAX_RETRIES} retries, aborting upload`);
            entry.error(`Part ${partNumber} network error after ${MAX_RETRIES} attempts. Upload aborted.`);
            hasError = true;
          }
        };

        xhr.open('PUT', url, true);
        xhr.send(chunk);
        activeUploads++;
      };

      // Upload next part if we haven't hit the concurrency limit
      const uploadNextPart = () => {
        while (partIndex < totalParts && activeUploads < MAX_CONCURRENT && !hasError) {
          uploadPart(partIndex);
          partIndex++;
        }
      };

      // Start initial batch of uploads
      uploadNextPart();
    });
  };
}
