"""Resume media downloads and preserve document attributes and still thumbnails."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from telethon import errors as telethon_errors
from telethon.tl import types

from . import progress as clone_progress
from . import state
from . import support as atomic
from .support import PolicyError, note
from .transfer import (
    CLONE_TRANSFER_PARALLEL,
    _photo_with_largest_size_last,
    download_resumable,
    media_byte_size,
    media_identity,
    upload_parts,
)

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
    except telethon_errors.FloodWaitError:
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
    """Per-clone reupload download cache. Survives a failed batch."""
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
