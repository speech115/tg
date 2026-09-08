"""Checkpointed serial download and bounded parallel upload of file parts."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from collections.abc import Callable, Coroutine, Iterable
from pathlib import Path
from typing import Any

from telethon import errors, helpers, utils
from telethon.tl import functions, types

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
    reordered = [size for size in photo.sizes if size is not largest]
    reordered.append(largest)
    new_photo = types.Photo(
        id=photo.id,
        access_hash=photo.access_hash,
        file_reference=photo.file_reference,
        date=photo.date,
        sizes=reordered,
        dc_id=photo.dc_id,
        has_stickers=photo.has_stickers or None,
        video_sizes=list(photo.video_sizes) if photo.video_sizes else None,
    )
    if isinstance(media, types.MessageMediaPhoto):
        return types.MessageMediaPhoto(
            spoiler=media.spoiler or None,
            live_photo=getattr(media, "live_photo", None) or None,
            photo=new_photo,
            ttl_seconds=media.ttl_seconds,
            video=getattr(media, "video", None),
        )
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
