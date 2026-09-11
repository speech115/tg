"""Resumable media transfer with bounded uploads and preserved document attributes."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
from collections.abc import Callable, Coroutine, Iterable
from copy import copy
from pathlib import Path
from typing import Any

from telethon import errors, helpers, utils
from telethon.tl import functions, types

from . import progress as clone_progress
from . import state
from . import support as atomic
from .support import PolicyError, note

CHUNK_SIZE = 512 * 1024
CLONE_TRANSFER_PARALLEL = 4
PROGRESS_EVERY_CHUNKS = 16


def _photo_with_largest_size_last(media):
    """Return media whose Photo.sizes ends with the true largest size."""
    photo = None
    if isinstance(media, types.MessageMediaPhoto):
        photo = media.photo
    elif isinstance(media, types.Photo):
        photo = media
    if not isinstance(photo, types.Photo) or len(photo.sizes) <= 1:
        return media
    largest = max(photo.sizes, key=lambda size: utils._photo_size_byte_count(size) or 0)
    if photo.sizes[-1] is largest:
        return media
    new_photo = copy(photo)
    new_photo.sizes = [size for size in photo.sizes if size is not largest] + [largest]
    if isinstance(media, types.MessageMediaPhoto):
        result = copy(media)
        result.photo = new_photo
        return result
    return new_photo


async def _run_workers(coros: Iterable[Coroutine[Any, Any, None]]) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for coro in coros:
                group.create_task(coro)
    except ExceptionGroup as eg:
        for error in eg.exceptions:
            if isinstance(error, errors.FloodWaitError):
                raise error
        raise eg.exceptions[0]


CHECKPOINT_EVERY_CHUNKS = 8


def _record(handle, checkpoint: Callable[[int], None], current: int) -> None:
    """Make ``current`` durable in the part file, then record it."""
    handle.flush()
    os.fsync(handle.fileno())
    checkpoint(current)


async def download_resumable(
    tg,
    media,
    part: Path,
    *,
    offset: int,
    size: int | None,
    checkpoint: Callable[[int], None],
    progress: Callable[[int, int | None], None] | None = None,
) -> int:
    """Append ``media`` into ``part`` from ``offset``; return the bytes on disk."""
    part.parent.mkdir(parents=True, exist_ok=True)
    with part.open("ab" if offset else "wb") as handle:
        current = offset
        chunks_since_checkpoint = 0
        chunks_since_progress = 0
        try:
            async for chunk in tg.iter_download(media, offset=offset, request_size=CHUNK_SIZE):
                handle.write(bytes(chunk))
                current = handle.tell()
                chunks_since_checkpoint += 1
                chunks_since_progress += 1
                if chunks_since_checkpoint >= CHECKPOINT_EVERY_CHUNKS:
                    _record(handle, checkpoint, current)
                    chunks_since_checkpoint = 0
                if progress is not None and chunks_since_progress >= PROGRESS_EVERY_CHUNKS:
                    progress(current, size)
                    chunks_since_progress = 0
        except BaseException:
            with contextlib.suppress(Exception):
                _record(handle, checkpoint, current)
            raise
        _record(handle, checkpoint, current)
        if progress is not None and chunks_since_progress:
            progress(current, size)
    return current


async def upload_parts(
    tg,
    path: Path | str,
    *,
    parallel: int = CLONE_TRANSFER_PARALLEL,
    file_name: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> types.TypeInputFile:
    """Upload ``path`` with up to ``parallel`` concurrent Save*FilePart RPCs."""
    if parallel < 1:
        raise ValueError("parallel must be positive")
    path = Path(path)
    file_size = path.stat().st_size
    part_size = int(utils.get_appropriated_part_size(file_size) * 1024)
    file_id = helpers.generate_random_long()
    name = file_name or path.name or str(file_id)
    is_big = file_size > 10 * 1024 * 1024
    part_count = max(1, (file_size + part_size - 1) // part_size)
    hash_md5 = hashlib.md5()
    if not is_big:
        hash_md5.update(path.read_bytes())
    uploaded = 0
    parts_since_progress = 0

    async def worker(index: int) -> None:
        nonlocal uploaded, parts_since_progress
        with path.open("rb") as handle:
            for part_index in range(index, part_count, parallel):
                handle.seek(part_index * part_size)
                part = handle.read(part_size)
                if is_big:
                    request: object = functions.upload.SaveBigFilePartRequest(
                        file_id, part_index, part_count, part
                    )
                else:
                    request = functions.upload.SaveFilePartRequest(file_id, part_index, part)
                result = await tg(request)
                if not result:
                    raise RuntimeError(f"Failed to upload file part {part_index}")
                uploaded += len(part)
                parts_since_progress += 1
                if progress is not None and parts_since_progress >= PROGRESS_EVERY_CHUNKS:
                    progress(uploaded, file_size)
                    parts_since_progress = 0

    worker_count = min(parallel, part_count)
    await _run_workers(worker(index) for index in range(worker_count))
    if progress is not None and parts_since_progress:
        progress(uploaded, file_size)
    if is_big:
        return types.InputFileBig(file_id, part_count, name)
    return types.InputFile(
        id=file_id, parts=part_count, name=name, md5_checksum=hash_md5.hexdigest()
    )


def media_identity(media) -> int | None:
    """Telegram's own id for a media object, or None when it has none."""
    for candidate in (getattr(media, "document", None), getattr(media, "photo", None), media):
        value = getattr(candidate, "id", None)
        if type(value) is int:
            return value
    return None


def media_byte_size(message) -> int | None:
    """Expected media byte size for download verification."""
    file = getattr(message, "file", None)
    size = getattr(file, "size", None)
    if isinstance(size, int) and size > 0:
        return size
    media = getattr(message, "media", None)
    document = getattr(media, "document", None)
    size = getattr(document, "size", None)
    if isinstance(size, int) and size > 0:
        return size
    return None


STILL_THUMB_SIZES = (types.PhotoSize, types.PhotoCachedSize, types.PhotoStrippedSize)


def thumb_weight(thumb) -> int:
    stored = getattr(thumb, "bytes", None)
    return len(stored) if stored is not None else getattr(thumb, "size", 0)


def document_thumb(document):
    """The document's largest still-image thumb size, or None."""
    stills = [
        thumb
        for thumb in getattr(document, "thumbs", None) or ()
        if isinstance(thumb, STILL_THUMB_SIZES)
    ]
    return max(stills, key=thumb_weight) if stills else None


async def uploaded_thumb(tg, message, document, path: Path):
    """Upload the source document's still preview, or None."""
    thumb = document_thumb(document)
    if thumb is None:
        return None
    try:
        downloaded = await tg.download_media(message, file=path, thumb=thumb)
        if downloaded is None:
            return None
        return await tg.upload_file(downloaded)
    except errors.FloodWaitError:
        raise
    except Exception as exc:
        note(f"warning: clone thumb skipped for source message {message.id}: {exc}")
        return None


async def uploaded_media(tg, message, path, progress=None):
    input_file = await upload_parts(
        tg,
        path,
        parallel=CLONE_TRANSFER_PARALLEL,
        progress=clone_progress.transfer_of(progress, message, "upload"),
    )
    if isinstance(message.media, types.MessageMediaPhoto):
        return types.InputMediaUploadedPhoto(file=input_file, spoiler=message.media.spoiler)
    document = message.media.document
    return types.InputMediaUploadedDocument(
        file=input_file,
        spoiler=message.media.spoiler,
        mime_type=getattr(document, "mime_type", None) or "application/octet-stream",
        attributes=list(getattr(document, "attributes", None) or ()),
        thumb=await uploaded_thumb(
            tg, message, document, Path(path).with_name(f"thumb-{message.id}")
        ),
    )


def cache_dir(clone_state: state.CloneState) -> Path:
    """Per-clone media download cache. Survives a failed batch."""
    return clone_state.store.root / "media" / clone_state.clone_id


def media_key(message):
    peer = getattr(message, "peer_id", None)
    if peer is None:
        raise PolicyError("source media has no peer identity")
    return {
        "peer": peer.to_dict(),
        "message": message.id,
        "kind": type(message.media).__name__,
        "media": media_identity(message.media),
        "size": media_byte_size(message),
    }


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def resume_offset(part, identity):
    record = _read(part.with_suffix(".offset"))
    offset = record.get("offset") if isinstance(record, dict) else None
    on_disk = part.stat().st_size if part.is_file() else -1
    if (
        type(offset) is not int
        or not 0 <= offset <= on_disk
        or record.get("identity") != identity
        or (identity["size"] is not None and offset > identity["size"])
    ):
        return 0
    with part.open("r+b") as handle:
        handle.truncate(offset)
    return offset


async def download_for_reupload(tg, message, workdir: Path, progress=None):
    identity = media_key(message)
    token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    target = workdir / f"{token}.bin"
    marker = target.with_suffix(".complete.json")
    record = _read(marker)
    if (
        isinstance(record, dict)
        and record.get("identity") == identity
        and target.is_file()
        and (target.stat().st_size == record.get("bytes"))
    ):
        return target
    part = target.with_suffix(".part")
    offset = resume_offset(part, identity)
    written = await download_resumable(
        tg,
        _photo_with_largest_size_last(message.media),
        part,
        offset=offset,
        size=identity["size"],
        checkpoint=lambda current: atomic.replace_text(
            part.with_suffix(".offset"), json.dumps({"identity": identity, "offset": current})
        ),
        progress=clone_progress.transfer_of(progress, message, "download"),
    )
    if written <= 0 or (identity["size"] is not None and written != identity["size"]):
        raise PolicyError(f"incomplete media download for message {message.id}: {written} bytes")
    os.replace(part, target)
    atomic.replace_text(marker, json.dumps({"identity": identity, "bytes": written}))
    part.with_suffix(".offset").unlink(missing_ok=True)
    return target
