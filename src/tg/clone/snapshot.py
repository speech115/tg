"""Text snapshots of polls and unavailable stories; optional reversible poll capture."""

from __future__ import annotations

import json

from telethon import errors as telethon_errors
from telethon import utils
from telethon.tl import functions, types

from .support import encode

BREAKDOWN_UNAVAILABLE = "распределение по вариантам недоступно"


def _vote_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "голос"
    if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14):
        return "голоса"
    return "голосов"


def _bar(percent: int, width: int = 10) -> str:
    eighths = round(percent * width * 8 / 100)
    full, remainder = divmod(eighths, 8)
    partial = ("", "▏", "▎", "▍", "▌", "▋", "▊", "▉")[remainder]
    empty = width - full - bool(remainder)
    return "█" * full + partial + "░" * empty


def _breakdown_available(results) -> bool:
    return bool(getattr(results, "results", None))


def _poll_snapshot(
    media: types.MessageMediaPoll, *, chosen_option: bytes | None = None
) -> tuple[str, list]:
    total = media.results.total_voters or 0
    raw_counts = {result.option: result.voters or 0 for result in media.results.results or ()}
    if chosen_option is not None and total > 0:
        total = max(0, total - 1)
        raw_counts = {
            option: max(0, voters - (1 if option == chosen_option else 0))
            for option, voters in raw_counts.items()
        }
    heading = "📊 Результаты опроса"
    question = media.poll.question.text
    if total > 0 and (not raw_counts):
        text = "\n\n".join([heading, question, BREAKDOWN_UNAVAILABLE, f"Проголосовало: {total}"])
        return (text, [])
    options = []
    for answer in media.poll.answers:
        voters = raw_counts.get(answer.option, 0)
        percent = round(voters * 100 / total) if total else 0
        options.append(
            f"{answer.text.text}\n{_bar(percent)} {percent}% · {voters} {_vote_word(voters)}"
        )
    text = "\n\n".join([heading, question, *options, f"Проголосовало: {total}"])
    return (text, [])


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _poll_eligible_for_vote(poll) -> bool:
    if getattr(poll, "closed", None):
        return False
    if getattr(poll, "quiz", None):
        return False
    if any(
        getattr(poll, flag, False)
        for flag in ("public_voters", "revoting_disabled", "hide_results_until_close")
    ):
        return False
    return True


def _results_from_updates(updates) -> types.PollResults | None:
    for item in getattr(updates, "updates", None) or ():
        if isinstance(item, types.UpdateMessagePoll):
            return item.results
    return None


async def recover_votes(tg, store, account_id):
    rows = store.conn.execute(
        "SELECT votes.clone, votes.data FROM votes JOIN clones ON clones.id=votes.clone"
    ).fetchall()
    for key, raw in rows:
        clone = store.load(key)
        if clone.account_user_id != account_id:
            continue
        vote = json.loads(raw)
        peer_id, peer_type = utils.resolve_id(vote["peer"])
        await tg(
            functions.messages.SendVoteRequest(
                peer=peer_type(peer_id), msg_id=vote["message"], options=[]
            )
        )
        with store.conn:
            store.conn.execute("DELETE FROM votes WHERE clone=?", (key,))
        clone.event("poll-retracted", {"message": vote["message"]})


async def _capture_breakdown(tg, message, media, peer, clone_state):
    option = bytes(media.poll.answers[0].option)
    store = clone_state.store
    vote = {"peer": utils.get_peer_id(peer), "message": message.id, "option": option.hex()}
    with store.conn:
        store.conn.execute("INSERT INTO votes VALUES (?,?)", (clone_state.clone_id, encode(vote)))
    try:
        updates = await tg(
            functions.messages.SendVoteRequest(peer=peer, msg_id=message.id, options=[option])
        )
    finally:
        await tg(functions.messages.SendVoteRequest(peer=peer, msg_id=message.id, options=[]))
        with store.conn:
            store.conn.execute("DELETE FROM votes WHERE clone=?", (clone_state.clone_id,))
    results = _results_from_updates(updates)
    if results is None or not _breakdown_available(results):
        return (media, None, {"message_id": message.id, "status": "capture_failed"})
    return (
        types.MessageMediaPoll(poll=media.poll, results=results),
        option,
        {"message_id": message.id, "status": "captured"},
    )


async def render(tg, message, *, peer=None, clone_state=None, capture_poll_votes=False):
    media = message.media
    if isinstance(media, types.MessageMediaPoll):
        marker, chosen, working = (None, None, media)
        needs_breakdown = (media.results.total_voters or 0) > 0 and (
            not _breakdown_available(media.results)
        )
        if needs_breakdown:
            if (
                capture_poll_votes
                and clone_state is not None
                and (peer is not None)
                and media.poll.answers
                and _poll_eligible_for_vote(media.poll)
            ):
                working, chosen, marker = await _capture_breakdown(
                    tg, message, media, peer, clone_state
                )
            else:
                marker = {
                    "message_id": message.id,
                    "status": "skipped",
                    "reason": "disabled" if not capture_poll_votes else "ineligible",
                }
        text, entities = _poll_snapshot(working, chosen_option=chosen)
        return (text, entities, marker)
    assert isinstance(media, types.MessageMediaStory), "render() requires fidelity.supports()"
    try:
        peer_entity = await tg.get_entity(media.peer)
    except telethon_errors.FloodWaitError:
        raise
    except (ValueError, telethon_errors.RPCError):
        peer_entity = None
    title = getattr(peer_entity, "title", None)
    name = " ".join(
        item
        for item in (
            getattr(peer_entity, "first_name", None),
            getattr(peer_entity, "last_name", None),
        )
        if item
    )
    username = getattr(peer_entity, "username", None)
    label = title or name or (f"@{username}" if username else "неизвестен")
    prefix = "Stories недоступна\nАвтор: "
    text = prefix + label
    entities = (
        [
            types.MessageEntityTextUrl(
                offset=_utf16_length(prefix),
                length=_utf16_length(label),
                url=f"https://t.me/{username}",
            )
        ]
        if username
        else []
    )
    return (text, entities, None)
