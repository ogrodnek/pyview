import datetime
import uuid
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal, Generator
from dataclasses import dataclass, field
from contextlib import contextmanager
import os
import tempfile


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
            except Exception as e:
                print("Error closing uploads", e)

            self.uploads = ActiveUploads()
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
        self, upload_name: str, constraints: UploadConstraints
    ) -> UploadConfig:
        config = UploadConfig(name=upload_name, constraints=constraints)
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
                    print("can't find ref", config.ref)

    def process_allow_upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        ref = payload["ref"]
        config = self.config_for_ref(ref)

        if not config:
            print("Can't find config for ref", ref)
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
                joinRef = config.uploads.join_ref_for_entry(entry_ref)
                del self.upload_config_join_refs[joinRef]

    def no_progress(self, joinRef) -> bool:
        config = self.upload_config_join_refs[joinRef]
        return config.uploads.no_progress()

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

    return Markup(
        f"""
       <input type="file" id="{config.ref}" name="{config.name}"
               data-phx-upload-ref="{config.ref}"
               data-phx-active-refs="{active_refs}"
               data-phx-done-refs="{done_refs}"
               data-phx-preflighted-refs="{preflighted_refs}"
               data-phx-update="ignore" phx-hook="Phoenix.LiveFileUpload"
               {accept} {multiple}>
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
