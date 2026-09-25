const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const bundle = readFileSync(path.join(__dirname, "../../static/assets/app.js"), "utf8");
const uploaders = readFileSync(path.join(__dirname, "../js/uploaders.js"), "utf8");

function loadBundledClass(context, name) {
  // Exercise the Phoenix classes we ship without booting the rest of the browser app.
  const start = bundle.indexOf(`  var ${name} = class {`);
  assert.notEqual(start, -1, `Missing bundled Phoenix class: ${name}`);
  const end = bundle.indexOf("\n  var ", start + 1);
  assert.notEqual(end, -1, `Missing end of bundled Phoenix class: ${name}`);
  vm.runInContext(bundle.slice(start, end), context);
}

function createUploadHarness() {
  const requests = [];
  const messages = [];
  const context = vm.createContext({
    window: {},
    console: { log() {}, error() {} },
    liveUploaderFileRef: 0,
    PHX_ACTIVE_ENTRY_REFS: "data-phx-active-refs",
    PHX_PREFLIGHTED_REFS: "data-phx-preflighted-refs",
    PHX_LIVE_FILE_UPDATED: "phx:live-file:updated",
    dom_default: {
      isAutoUpload: () => false,
      private: (input, key) => input.privateData[key],
      putPrivate: (input, key, value) => { input.privateData[key] = value; },
    },
    XMLHttpRequest: class {
      constructor() {
        this.upload = { addEventListener() {} };
      }
      open() {}
      send() { requests.push(this); }
      abort() {}
      getResponseHeader() { return this.etag; }
      succeed(etag) {
        this.status = 200;
        this.etag = `"${etag}"`;
        this.onload();
      }
    },
  });
  loadBundledClass(context, "UploadEntry");
  loadBundledClass(context, "LiveUploader");
  vm.runInContext(uploaders, context);

  const view = {
    pushFileProgress(input, ref, progress, onReply) {
      messages.push({
        ref,
        progress: JSON.parse(JSON.stringify(progress)),
        acknowledge: () => onReply?.(),
      });
    },
  };

  function startUpload(name = "example.pdf") {
    const file = new Blob(["abcd"]);
    file.name = name;
    const ref = context.LiveUploader.genFileRef(file);
    const attributes = new Map([
      ["data-phx-active-refs", ref],
      ["data-phx-preflighted-refs", ""],
    ]);
    const input = Object.assign(new EventTarget(), {
      privateData: {},
      getAttribute: (name) => attributes.get(name) ?? null,
    });
    context.LiveUploader.trackFiles(input, [file]);
    let formReadyCount = 0;
    const uploader = new context.LiveUploader(input, view, () => formReadyCount++);
    uploader.initAdapterUpload(
      { entries: { [ref]: {
        uploader: "S3Multipart",
        upload_id: `upload-${ref}`,
        key: name,
        part_urls: ["https://example.com/part-1", "https://example.com/part-2"],
        chunk_size: 2,
      } } },
      () => {},
      { uploaders: context.window.Uploaders },
    );
    return {
      entry: uploader.entries()[0],
      get formReadyCount() { return formReadyCount; },
      get trackedFiles() { return context.LiveUploader.activeFiles(input); },
      get entriesInProgress() { return uploader.numEntriesInProgress; },
      removeFromServerSelection() {
        attributes.set("data-phx-active-refs", "");
        input.dispatchEvent(new Event("phx:live-file:updated"));
      },
    };
  }

  return {
    startUpload,
    requests,
    messages,
    view,
    get completions() {
      return messages.filter(({ progress }) => progress === 100 || progress.complete);
    },
  };
}

test("multipart completion lets the form continue after the server acknowledges it", () => {
  // Given a multipart upload with two parts that finish out of order
  const harness = createUploadHarness();
  const upload = harness.startUpload();
  harness.requests[1].succeed("second-etag");
  harness.requests[0].succeed("first-etag");

  // Then the server receives the ordered parts once, while the form still waits for its reply
  assert.equal(harness.completions.length, 1);
  assert.deepEqual(harness.completions[0].progress, {
    complete: true,
    upload_id: "upload-0",
    key: "example.pdf",
    parts: [
      { PartNumber: 1, ETag: "first-etag" },
      { PartNumber: 2, ETag: "second-etag" },
    ],
  });
  assert.equal(upload.formReadyCount, 0);
  assert.equal(upload.trackedFiles.length, 1);

  // When the server acknowledges multipart completion
  harness.completions[0].acknowledge();

  // Then the browser finishes the upload and releases the form without another completion message
  assert.equal(upload.entry.isDone(), true);
  assert.equal(upload.entry.isCancelled(), false);
  assert.equal(upload.formReadyCount, 1);
  assert.equal(upload.entriesInProgress, 0);
  assert.equal(upload.trackedFiles.length, 0);
  assert.equal(harness.completions.length, 1);
});

test("consuming the upload during the server reply does not finish the browser entry twice", () => {
  // Given a multipart upload whose parts have finished uploading
  const harness = createUploadHarness();
  const upload = harness.startUpload();
  harness.requests[0].succeed("first-etag");
  harness.requests[1].succeed("second-etag");

  // When the server consumes the entry and its rendered update arrives before the reply callback
  upload.removeFromServerSelection();
  harness.completions[0].acknowledge();

  // Then the form is released once and the upload is fully removed from browser tracking
  assert.equal(upload.formReadyCount, 1);
  assert.equal(upload.entriesInProgress, 0);
  assert.equal(upload.trackedFiles.length, 0);
  assert.equal(harness.completions.length, 1);
});

test("completing one multipart upload preserves another upload on the same view", () => {
  // Given two multipart uploads sharing the same LiveView
  const harness = createUploadHarness();
  const first = harness.startUpload("first.pdf");
  const second = harness.startUpload("second.pdf");
  const pushProgress = harness.view.pushFileProgress;

  // When the first upload completes while the second is still underway
  harness.requests[0].succeed("first-part");
  harness.requests[1].succeed("second-part");
  harness.completions[0].acknowledge();

  // Then only the first form is ready and the shared view keeps its normal progress handling
  assert.equal(first.formReadyCount, 1);
  assert.equal(second.formReadyCount, 0);
  assert.equal(first.entry.view, harness.view);
  assert.equal(second.entry.view, harness.view);
  assert.equal(harness.view.pushFileProgress, pushProgress);

  // When the second upload finishes
  harness.requests[2].succeed("third-part");
  harness.requests[3].succeed("fourth-part");
  harness.completions[1].acknowledge();

  // Then it completes independently with its own multipart details
  assert.equal(first.formReadyCount, 1);
  assert.equal(second.formReadyCount, 1);
  assert.equal(harness.completions.length, 2);
  assert.equal(harness.completions[1].progress.key, "second.pdf");
  assert.equal(second.trackedFiles.length, 0);
});
