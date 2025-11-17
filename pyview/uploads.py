import datetime
import logging
import os
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generator, Literal, Optional

from markupsafe import Markup
from pydantic import BaseModel, Field

from pyview.vendor.ibis import filters

logger = logging.getLogger(__name__)


@dataclass
class UploadSuccess:
    """Upload completed successfully (no additional data needed)."""

    pass


@dataclass
class UploadSuccessWithData:
    """Upload completed successfully with completion data.

    Used for multipart uploads where the client sends additional data like:
    - upload_id: S3 multipart upload ID
    - parts: List of {PartNumber, ETag} dicts
    - key: S3 object key
    - Any other provider-specific fields
    """

    data: dict


@dataclass
class UploadFailure:
    """Upload failed with an error.

    Used when the client reports an upload error.
    """

    error: str


# Type alias for upload completion results
UploadResult = UploadSuccess | UploadSuccessWithData | UploadFailure


@dataclass
class ConstraintViolation:
    ref: str
    code: Literal["too_large", "too_many_files", "upload_failed"]

    @property
    def message(self) -> str:
        if self.code == "too_large":
            return "File too large"
        if self.code == "too_many_files":
            return "Too many files"
        if self.code == "upload_failed":
            return "Upload failed"
        return self.code


class UploadEntry(BaseModel):
    ref: str
    name: str
    size: int
    type: str
    path: Optional[str] = None  # None for external uploads, set for internal uploads
    upload_config: Optional["UploadConfig"] = None
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    valid: bool = True
    errors: list[ConstraintViolation] = Field(default_factory=list)
    progress: int = 0
    preflighted: bool = False
    cancelled: bool = False
    done: bool = False
    last_modified: int = Field(default_factory=lambda: int(datetime.datetime.now().timestamp()))
    meta: Optional["ExternalUploadMeta"] = None  # Metadata from external uploads


def parse_entries(entries: list[dict]) -> list[UploadEntry]:
    return [UploadEntry(**entry) for entry in entries]


@dataclass
class ActiveUpload:
    ref: str
    entry: UploadEntry
    file: tempfile._TemporaryFileWrapper = field(init=False)

    def __post_init__(self):
        self.file = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115

    def close(self):
        self.file.close()
        os.remove(self.file.name)


@dataclass
class ActiveUploads:
    uploads: dict[str, ActiveUpload] = field(default_factory=dict)

    def add_upload(self, ref: str, entry: UploadEntry):
        self.uploads[ref] = ActiveUpload(ref, entry)

    def add_chunk(self, ref: str, chunk: bytes):
        self.uploads[ref].file.write(chunk)
        self.uploads[ref].file.flush()
        self.uploads[ref].entry.progress = self.uploads[ref].file.tell()

    def no_progress(self) -> bool:
        return all(upload.entry.progress == 0 for upload in self.uploads.values())

    def file_name(self, ref: str) -> str:
        return self.uploads[ref].file.name

    def join_ref_for_entry(self, ref: str) -> str:
        return [join_ref for join_ref, upload in self.uploads.items() if upload.entry.ref == ref][0]

    def close(self):
        for upload in self.uploads.values():
            upload.close()


class ExternalUploadMeta(BaseModel):
    """Metadata returned by external upload presign functions.

    The 'uploader' field is required and specifies the name of the client-side
    JavaScript uploader (e.g., "S3", "GCS", "Azure").

    Additional provider-specific fields (url, fields, etc.) can be added as needed.
    """

    uploader: str  # Required - name of client-side JS uploader

    # Allow extra fields for provider-specific data (url, fields, etc.)
    model_config = {"extra": "allow"}


class UploadConstraints(BaseModel):
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_files: int = 10
    accept: list[str] = Field(default_factory=lambda: ["image/*"])
    chunk_size: int = 64 * 1024  # 64KB


class UploadConfig(BaseModel):
    name: str

    entries_by_ref: dict[str, UploadEntry] = Field(default_factory=dict)
    ref: str = Field(default_factory=lambda: str(uuid.uuid4()))
    errors: list[ConstraintViolation] = Field(default_factory=list)
    autoUpload: bool = False
    constraints: UploadConstraints = Field(default_factory=UploadConstraints)
    progress_callback: Optional[Callable[[UploadEntry, Any], Awaitable[None]]] = None
    external_callback: Optional[Callable[[UploadEntry, Any], Awaitable[ExternalUploadMeta]]] = None
    entry_complete_callback: Optional[
        Callable[[UploadEntry, UploadResult, Any], Awaitable[None]]
    ] = None

    uploads: ActiveUploads = Field(default_factory=ActiveUploads)

    @property
    def entries(self) -> list[UploadEntry]:
        return list(self.entries_by_ref.values())

    @property
    def is_external(self) -> bool:
        """Returns True if this upload config uses external (direct-to-cloud) uploads"""
        return self.external_callback is not None

    def cancel_entry(self, ref: str):
        del self.entries_by_ref[ref]

        # recheck constraints
        self.errors.clear()
        if len(self.entries_by_ref) > self.constraints.max_files:
            self.errors.append(ConstraintViolation(ref=self.ref, code="too_many_files"))

    def add_entries(self, entries: list[dict]):
        parsed = parse_entries(entries)
        for entry in parsed:
            entry.upload_config = self
            self.entries_by_ref[entry.ref] = entry
            if entry.size > self.constraints.max_file_size:
                entry.valid = False
                entry.errors.append(ConstraintViolation(ref=entry.ref, code="too_large"))

        if len(self.entries_by_ref) > self.constraints.max_files:
            self.errors.append(ConstraintViolation(ref=self.ref, code="too_many_files"))

    def update_progress(self, ref: str, progress: int):
        if ref in self.entries_by_ref:
            self.entries_by_ref[ref].progress = progress
            self.entries_by_ref[ref].done = progress == 100

    @contextmanager
    def consume_uploads(self) -> Generator[list["ActiveUpload"], None, None]:
        try:
            upload_list = list(self.uploads.uploads.values())
            yield upload_list
        finally:
            try:
                self.uploads.close()
            except Exception:
                logger.warning("Error closing uploads", exc_info=True)

            self.uploads = ActiveUploads()
            self.entries_by_ref = {}

    @contextmanager
    def consume_upload_entry(
        self, entry_ref: str
    ) -> Generator[Optional["ActiveUpload"], None, None]:
        """Consume a single upload entry by its ref"""
        upload = None
        join_ref = None

        # Find the join_ref for this entry
        for jr, active_upload in self.uploads.uploads.items():
            if active_upload.entry.ref == entry_ref:
                upload = active_upload
                join_ref = jr
                break

        try:
            yield upload
        finally:
            if upload and join_ref:
                try:
                    upload.close()
                except Exception:
                    logger.warning("Error closing upload entry", exc_info=True)

                # Remove only this specific upload
                if join_ref in self.uploads.uploads:
                    del self.uploads.uploads[join_ref]
                if entry_ref in self.entries_by_ref:
                    del self.entries_by_ref[entry_ref]

    @contextmanager
    def consume_external_upload(
        self, entry_ref: str
    ) -> Generator[Optional["UploadEntry"], None, None]:
        """Consume a single external upload entry by its ref.

        For external uploads (direct-to-cloud), this returns the UploadEntry containing
        metadata about the uploaded file. The entry is automatically removed after the
        context manager exits.

        Args:
            entry_ref: The ref of the entry to consume

        Yields:
            UploadEntry if found, None otherwise

        Raises:
            ValueError: If called on a non-external upload config
        """
        if not self.is_external:
            raise ValueError(
                "consume_external_upload() can only be called on external upload configs"
            )

        entry = self.entries_by_ref.get(entry_ref)

        try:
            yield entry
        finally:
            if entry_ref in self.entries_by_ref:
                del self.entries_by_ref[entry_ref]

    @contextmanager
    def consume_external_uploads(self) -> Generator[list["UploadEntry"], None, None]:
        """Consume all external upload entries and clean up.

        For external uploads (direct-to-cloud), this returns the UploadEntry objects
        containing metadata about the uploaded files. The entries are automatically
        cleared after the context manager exits.

        Yields:
            List of UploadEntry objects

        Raises:
            ValueError: If called on a non-external upload config
        """
        if not self.is_external:
            raise ValueError(
                "consume_external_uploads() can only be called on external upload configs"
            )

        try:
            upload_list = list(self.entries_by_ref.values())
            yield upload_list
        finally:
            self.entries_by_ref = {}

    def close(self):
        self.uploads.close()


class UploadManager:
    upload_configs: dict[str, UploadConfig]
    upload_config_join_refs: dict[str, UploadConfig]

    def __init__(self):
        self.upload_configs = {}
        self.upload_config_join_refs = {}

    def allow_upload(
        self,
        upload_name: str,
        constraints: UploadConstraints,
        auto_upload: bool = False,
        progress: Optional[Callable] = None,
        external: Optional[Callable] = None,
        entry_complete: Optional[Callable] = None,
    ) -> UploadConfig:
        config = UploadConfig(
            name=upload_name,
            constraints=constraints,
            autoUpload=auto_upload,
            progress_callback=progress,
            external_callback=external,
            entry_complete_callback=entry_complete,
        )
        self.upload_configs[upload_name] = config
        return config

    def config_for_name(self, upload_name: str) -> Optional[UploadConfig]:
        return self.upload_configs.get(upload_name)

    def config_for_ref(self, ref: str) -> Optional[UploadConfig]:
        return [c for c in self.upload_configs.values() if c.ref == ref][0]

    def maybe_process_uploads(self, qs: dict[str, Any], payload: dict[str, Any]):
        if "uploads" in payload:
            uploads = payload["uploads"]
            config_key = qs["_target"][0]

            config = self.config_for_name(config_key)
            if config:
                if config.ref in uploads:
                    entries = uploads[config.ref]
                    config.add_entries(entries)
                else:
                    logger.warning("Upload config not found for ref: %s", config.ref)

    def _validate_constraints(
        self, config: UploadConfig, proposed_entries: list[dict[str, Any]]
    ) -> list[ConstraintViolation]:
        """Validate proposed entries against upload constraints."""
        errors = []
        for entry in proposed_entries:
            if entry["size"] > config.constraints.max_file_size:
                errors.append(ConstraintViolation(ref=entry["ref"], code="too_large"))

        if len(proposed_entries) > config.constraints.max_files:
            errors.append(ConstraintViolation(ref=config.ref, code="too_many_files"))

        return errors

    async def _process_external_upload(
        self, config: UploadConfig, proposed_entries: list[dict[str, Any]], context: Any
    ) -> dict[str, Any]:
        """Process external (direct-to-cloud) upload by calling presign function for each entry."""
        entries_with_meta = {}
        successfully_preflighted = []  # Track entries added to config for atomic cleanup

        if not config.external_callback:
            logger.error("external_callback is required for external uploads")
            return {"error": [("config", "external_callback_missing")]}

        for entry_data in proposed_entries:
            # Create UploadEntry to pass to presign function
            entry = UploadEntry(**entry_data)
            entry.upload_config = config

            try:
                # Call user's presign function
                meta: ExternalUploadMeta = await config.external_callback(entry, context)

                # Store metadata and mark entry as preflighted
                entry.meta = meta
                entry.preflighted = True
                config.entries_by_ref[entry.ref] = entry
                successfully_preflighted.append(entry.ref)  # Track for cleanup

                # Build entry JSON with metadata merged at top level
                entry_dict = entry.model_dump(exclude={"upload_config", "meta"})
                entry_dict.update(meta.model_dump())  # Merge meta fields into entry
                entries_with_meta[entry.ref] = entry_dict

            except Exception as e:
                logger.error(
                    f"Error calling presign function for entry {entry.ref}: {e}", exc_info=True
                )

                # Atomic cleanup: remove all entries added before this failure
                for ref in successfully_preflighted:
                    config.entries_by_ref.pop(ref, None)

                return {"error": [(entry.ref, "presign_error")]}

        configJson = config.constraints.model_dump()
        return {"config": configJson, "entries": entries_with_meta}

    def _process_internal_upload(self, config: UploadConfig) -> dict[str, Any]:
        """Process internal (direct-to-server) upload."""
        configJson = config.constraints.model_dump()
        entryJson = {e.ref: e.model_dump(exclude={"upload_config"}) for e in config.entries}
        return {"config": configJson, "entries": entryJson}

    async def process_allow_upload(self, payload: dict[str, Any], context: Any) -> dict[str, Any]:
        """Process allow_upload request from client.

        Validates constraints and either:
        - For external uploads: calls presign function to generate upload metadata
        - For internal uploads: returns standard config/entries response
        """
        ref = payload["ref"]
        config = self.config_for_ref(ref)

        if not config:
            logger.warning("Can't find upload config for ref: %s", ref)
            return {"error": [(ref, "not_found")]}

        proposed_entries = payload["entries"]

        # Validate constraints
        errors = self._validate_constraints(config, proposed_entries)
        if errors:
            return {"error": [(e.ref, e.code) for e in errors]}

        # Handle external vs internal uploads
        if config.is_external:
            return await self._process_external_upload(config, proposed_entries, context)
        else:
            return self._process_internal_upload(config)

    def add_upload(self, joinRef: str, payload: dict[str, Any]):
        token = payload["token"]

        config = self.config_for_name(token["path"])
        if config:
            self.upload_config_join_refs[joinRef] = config
            entry = UploadEntry(**token)
            config.uploads.add_upload(joinRef, entry)

    def add_chunk(self, joinRef: str, chunk: bytes):
        config = self.upload_config_join_refs[joinRef]
        config.uploads.add_chunk(joinRef, chunk)
        pass

    async def update_progress(self, joinRef: str, payload: dict[str, Any], socket):
        upload_config_ref = payload["ref"]
        entry_ref = payload["entry_ref"]
        progress_data = payload["progress"]

        config = self.config_for_ref(upload_config_ref)
        if not config:
            logger.warning(f"[update_progress] No config found for ref: {upload_config_ref}")
            return

        # Handle dict (error or completion)
        if isinstance(progress_data, dict):
            if progress_data.get("complete"):
                entry = config.entries_by_ref.get(entry_ref)
                if entry:
                    entry.progress = 100
                    entry.done = True

                    # Call entry_complete callback with success result
                    if config.entry_complete_callback:
                        result = UploadSuccessWithData(data=progress_data)
                        await config.entry_complete_callback(entry, result, socket)
                return

            # Handle error case: {error: "reason"}
            error_msg = progress_data.get("error", "Upload failed")
            logger.warning(f"Upload error for entry {entry_ref}: {error_msg}")

            if entry_ref in config.entries_by_ref:
                entry = config.entries_by_ref[entry_ref]
                entry.valid = False
                entry.done = True
                entry.errors.append(ConstraintViolation(ref=entry_ref, code="upload_failed"))

                # Call entry_complete callback with failure result
                if config.entry_complete_callback:
                    result = UploadFailure(error=error_msg)
                    await config.entry_complete_callback(entry, result, socket)
            return

        # Handle progress number
        progress = int(progress_data)
        config.update_progress(entry_ref, progress)

        # Fire entry_complete callback on 100
        if progress == 100:
            entry = config.entries_by_ref.get(entry_ref)
            if entry and config.entry_complete_callback:
                result = UploadSuccess()
                await config.entry_complete_callback(entry, result, socket)

            # Cleanup for internal uploads only (external uploads never populate upload_config_join_refs)
            if not config.is_external:
                try:
                    joinRef_to_remove = config.uploads.join_ref_for_entry(entry_ref)
                    if joinRef_to_remove in self.upload_config_join_refs:
                        del self.upload_config_join_refs[joinRef_to_remove]
                except (IndexError, KeyError):
                    # Entry might have already been consumed and removed
                    pass

    def no_progress(self, joinRef) -> bool:
        config = self.upload_config_join_refs[joinRef]
        return config.uploads.no_progress()

    async def trigger_progress_callback_if_exists(self, payload: dict[str, Any], socket):
        """Trigger progress callback if one exists for this upload config"""
        upload_config_ref = payload["ref"]
        config = self.config_for_ref(upload_config_ref)

        if config and config.progress_callback:
            entry_ref = payload["entry_ref"]
            if entry_ref in config.entries_by_ref:
                entry = config.entries_by_ref[entry_ref]
                progress_data = payload["progress"]

                # Update entry progress before calling callback
                if isinstance(progress_data, int):
                    entry.progress = progress_data
                    entry.done = progress_data == 100
                # For dict (error or completion), don't update entry.progress here
                # (will be handled in update_progress or completion handler)

                await config.progress_callback(entry, socket)

    def close(self):
        for config in self.upload_configs.values():
            config.close()
        self.upload_configs = {}


@filters.register
def live_file_input(config: Optional[UploadConfig]) -> Markup:
    if not config:
        return Markup("")

    active_refs = ",".join([entry.ref for entry in config.entries])
    done_refs = ",".join([entry.ref for entry in config.entries if entry.done])
    preflighted_refs = ",".join([entry.ref for entry in config.entries if entry.preflighted])
    accepted = ",".join(config.constraints.accept)
    accept = f'accept="{accepted}"' if accepted else ""
    multiple = "multiple" if config.constraints.max_files > 1 else ""
    auto_upload = "data-phx-auto-upload" if config.autoUpload else ""

    return Markup(
        f"""
       <input type="file" id="{config.ref}" name="{config.name}"
               data-phx-upload-ref="{config.ref}"
               data-phx-active-refs="{active_refs}"
               data-phx-done-refs="{done_refs}"
               data-phx-preflighted-refs="{preflighted_refs}"
               data-phx-update="ignore" phx-hook="Phoenix.LiveFileUpload"
               {accept} {multiple} {auto_upload}>
            </input>
        """
    )


@filters.register
def upload_preview_tag(entry: UploadEntry) -> Markup:
    config_ref = entry.upload_config.ref if entry.upload_config else ""
    return Markup(
        f"""<img id="phx-preview-{entry.ref}" data-phx-upload-ref="{config_ref}"
            data-phx-entry-ref="{entry.ref}" data-phx-hook="Phoenix.LiveImgPreview" data-phx-update="ignore" />
        """
    )
