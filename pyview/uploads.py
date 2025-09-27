import datetime
import uuid
import logging
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal, Generator, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager
import os
import tempfile

logger = logging.getLogger(__name__)


@dataclass
class ConstraintViolation:
    ref: str
    code: Literal["too_large", "too_many_files"]

    @property
    def message(self) -> str:
        if self.code == "too_large":
            return "File too large"
        return "Too many files"


class UploadEntry(BaseModel):
    path: str
    ref: str
    name: str
    size: int
    type: str
    upload_config: Optional["UploadConfig"] = None
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    valid: bool = True
    errors: list[ConstraintViolation] = Field(default_factory=list)
    progress: int = 0
    preflighted: bool = False
    cancelled: bool = False
    done: bool = False
    last_modified: int = Field(
        default_factory=lambda: int(datetime.datetime.now().timestamp())
    )


def parse_entries(entries: list[dict]) -> list[UploadEntry]:
    return [UploadEntry(**entry) for entry in entries]


@dataclass
class ActiveUpload:
    ref: str
    entry: UploadEntry
    file: tempfile._TemporaryFileWrapper = field(init=False)

    def __post_init__(self):
        self.file = tempfile.NamedTemporaryFile(delete=False)

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
        return [
            join_ref
            for join_ref, upload in self.uploads.items()
            if upload.entry.ref == ref
        ][0]

    def close(self):
        for upload in self.uploads.values():
            upload.close()


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
    progress_callback: Optional[Callable] = None

    uploads: ActiveUploads = Field(default_factory=ActiveUploads)

    @property
    def entries(self) -> list[UploadEntry]:
        return list(self.entries_by_ref.values())

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
                entry.errors.append(
                    ConstraintViolation(ref=entry.ref, code="too_large")
                )

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
    def consume_upload_entry(self, entry_ref: str) -> Generator[Optional["ActiveUpload"], None, None]:
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

    def close(self):
        self.uploads.close()


class UploadManager:
    upload_configs: dict[str, UploadConfig]
    upload_config_join_refs: dict[str, UploadConfig]

    def __init__(self):
        self.upload_configs = {}
        self.upload_config_join_refs = {}

    def allow_upload(
        self, upload_name: str, constraints: UploadConstraints, auto_upload: bool = False, progress: Optional[Callable] = None
    ) -> UploadConfig:
        config = UploadConfig(name=upload_name, constraints=constraints, autoUpload=auto_upload, progress_callback=progress)
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

    def process_allow_upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        ref = payload["ref"]
        config = self.config_for_ref(ref)

        if not config:
            logger.warning("Can't find upload config for ref: %s", ref)
            return {"error": [(ref, "not_found")]}

        proposed_entries = payload["entries"]

        errors = []
        for entry in proposed_entries:
            if entry["size"] > config.constraints.max_file_size:
                errors.append(ConstraintViolation(ref=entry["ref"], code="too_large"))

        if len(proposed_entries) > config.constraints.max_files:
            errors.append(ConstraintViolation(ref=ref, code="too_many_files"))

        if errors:
            return {"error": [(e.ref, e.code) for e in errors]}

        configJson = config.constraints.model_dump()
        entryJson = {
            e.ref: e.model_dump(exclude={"upload_config"}) for e in config.entries
        }

        return {"config": configJson, "entries": entryJson}

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

    def update_progress(self, joinRef: str, payload: dict[str, Any]):
        upload_config_ref = payload["ref"]
        entry_ref = payload["entry_ref"]
        progress = int(payload["progress"])

        config = self.config_for_ref(upload_config_ref)
        if config:
            config.update_progress(entry_ref, progress)

            if progress == 100:
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
                # Update entry progress before calling callback
                progress = int(payload["progress"])
                entry.progress = progress
                entry.done = progress == 100
                await config.progress_callback(entry, socket)

    def close(self):
        for config in self.upload_configs.values():
            config.close()
        self.upload_configs = {}


from markupsafe import Markup
from pyview.vendor.ibis import filters


@filters.register
def live_file_input(config: Optional[UploadConfig]) -> Markup:
    if not config:
        return Markup("")

    active_refs = ",".join([entry.ref for entry in config.entries])
    done_refs = ",".join([entry.ref for entry in config.entries if entry.done])
    preflighted_refs = ",".join(
        [entry.ref for entry in config.entries if entry.preflighted]
    )
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
