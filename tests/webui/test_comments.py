"""
Unit tests for webui/stats.py's comment listing/moderation functions
(list_comments, set_comment_moderation, reply_to_comment,
delete_comment). Never hits the real YouTube API -- every function takes an
optional `client=` kwarg that, when supplied, is used as-is instead of
building a real googleapiclient client from token.json, so these tests pass
small hand-written fakes that mimic the googleapiclient chained-call shape
(resource().method(**kwargs).execute()).
"""
from __future__ import annotations

import pytest

from webui import stats


@pytest.fixture(autouse=True)
def _clear_comment_cache():
    stats._comments_cache.clear()
    yield
    stats._comments_cache.clear()


class _Exec:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _ThreadsResource:
    """Fakes youtube.commentThreads() -- .list(**kw).execute() returns pages
    in order, following nextPageToken like the real API."""

    def __init__(self, pages):
        self.pages = pages
        self.list_calls: list[dict] = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        token = kwargs.get("pageToken")
        idx = 0 if not token else int(token)
        return _Exec(self.pages[idx])


class _RaisingThreadsResource:
    def list(self, **kwargs):
        raise RuntimeError("simulated API error")


class FakeClient:
    """Fakes the youtube#v3 client for both commentThreads() and comments()."""

    def __init__(self, thread_pages=None, comment_list_pages=None):
        self._threads = _ThreadsResource(thread_pages or [])
        self._comment_list_pages = comment_list_pages or []
        self.list_calls: list[dict] = []
        self.moderation_calls: list[tuple] = []
        self.insert_bodies: list[dict] = []
        self.delete_ids: list[str] = []

    def commentThreads(self):
        return self._threads

    def comments(self):
        return self

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        token = kwargs.get("pageToken")
        idx = 0 if not token else int(token)
        return _Exec(self._comment_list_pages[idx])

    def setModerationStatus(self, id, moderationStatus):  # noqa: N803 -- matches API kwarg name
        self.moderation_calls.append((id, moderationStatus))
        return _Exec({})

    def insert(self, part, body):
        self.insert_bodies.append(body["snippet"])
        return _Exec({
            "id": "new_reply_1",
            "snippet": {
                "authorDisplayName": "Channel Owner",
                "textDisplay": body["snippet"]["textOriginal"],
                "likeCount": 0,
            },
        })

    def delete(self, id):  # noqa: A002 -- matches API kwarg name
        self.delete_ids.append(id)
        return _Exec({})


def _thread_page(items, next_token=None):
    page = {"items": items}
    if next_token:
        page["nextPageToken"] = next_token
    return page


def _thread_item(comment_id, author="Alice", text="Great video!", likes=3,
                  reply_count=0, replies=None):
    item = {
        "snippet": {
            "topLevelComment": {
                "id": comment_id,
                "snippet": {
                    "authorDisplayName": author,
                    "textDisplay": text,
                    "likeCount": likes,
                    "publishedAt": "2026-08-01T00:00:00Z",
                    "moderationStatus": "published",
                },
            },
            "totalReplyCount": reply_count,
        },
    }
    if replies:
        item["replies"] = {"comments": replies}
    return item


def _reply_item(reply_id, author="Bob", text="Agreed", likes=1):
    return {"id": reply_id, "snippet": {
        "authorDisplayName": author, "textDisplay": text, "likeCount": likes,
    }}


# ── list_comments ───────────────────────────────────────────────────────────
def test_list_comments_shapes_threads_and_inline_replies():
    page = _thread_page([
        _thread_item("c1", reply_count=1, replies=[_reply_item("r1")]),
    ])
    client = FakeClient(thread_pages=[page])

    result = stats.list_comments("vid1", client=client)

    assert result == [{
        "id": "c1", "author": "Alice", "author_avatar": None,
        "text": "Great video!", "like_count": 3,
        "published_at": "2026-08-01T00:00:00Z", "moderation_status": "published",
        "reply_count": 1,
        "replies": [{
            "id": "r1", "author": "Bob", "author_avatar": None, "text": "Agreed",
            "like_count": 1, "published_at": None, "moderation_status": "published",
        }],
    }]


def test_list_comments_paginates_across_pages():
    page1 = _thread_page([_thread_item("t1")], next_token="1")
    page2 = _thread_page([_thread_item("t2")])
    client = FakeClient(thread_pages=[page1, page2])

    result = stats.list_comments("vid_page", client=client)

    assert [c["id"] for c in result] == ["t1", "t2"]


def test_list_comments_empty_video_returns_empty_list_not_none():
    client = FakeClient(thread_pages=[_thread_page([])])
    result = stats.list_comments("vid_empty", client=client)
    assert result == []


def test_list_comments_returns_none_on_api_error():
    class Client:
        def commentThreads(self):
            return _RaisingThreadsResource()

    assert stats.list_comments("vid_err", client=Client()) is None


def test_list_comments_caches_within_ttl():
    page = _thread_page([_thread_item("c1")])
    client = FakeClient(thread_pages=[page])

    first = stats.list_comments("vid_cache", client=client)
    second = stats.list_comments("vid_cache", client=client)

    assert first == second
    assert len(client._threads.list_calls) == 1  # second call served from cache


def test_list_comments_force_bypasses_cache():
    page = _thread_page([_thread_item("c1")])
    client = FakeClient(thread_pages=[page, page])

    stats.list_comments("vid_force", client=client)
    stats.list_comments("vid_force", force=True, client=client)

    assert len(client._threads.list_calls) == 2




# ── set_comment_moderation ───────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["heldForReview", "published", "rejected"])
def test_set_comment_moderation_accepts_documented_statuses(status):
    client = FakeClient()
    assert stats.set_comment_moderation("c1", status, client=client) is True
    assert client.moderation_calls == [("c1", status)]


def test_set_comment_moderation_rejects_unknown_status():
    client = FakeClient()
    assert stats.set_comment_moderation("c1", "bogus_status", client=client) is False
    assert client.moderation_calls == []


def test_set_comment_moderation_false_on_api_error():
    class Client:
        def comments(self):
            raise RuntimeError("boom")

    assert stats.set_comment_moderation("c1", "published", client=Client()) is False


# ── reply_to_comment ─────────────────────────────────────────────────────────
def test_reply_to_comment_posts_and_shapes_result():
    client = FakeClient()
    result = stats.reply_to_comment("c1", "Thanks for watching!", client=client)

    assert result["text"] == "Thanks for watching!"
    assert result["author"] == "Channel Owner"
    assert client.insert_bodies == [{"parentId": "c1", "textOriginal": "Thanks for watching!"}]


def test_reply_to_comment_blank_text_is_a_noop():
    client = FakeClient()
    result = stats.reply_to_comment("c1", "   ", client=client)

    assert result is None
    assert client.insert_bodies == []


# ── delete_comment ───────────────────────────────────────────────────────────
def test_delete_comment_calls_api_and_returns_true():
    client = FakeClient()
    assert stats.delete_comment("c1", client=client) is True
    assert client.delete_ids == ["c1"]


def test_delete_comment_false_on_api_error():
    class Client:
        def comments(self):
            raise RuntimeError("boom")

    assert stats.delete_comment("c1", client=Client()) is False


def test_moderation_action_invalidates_comment_cache():
    page = _thread_page([_thread_item("c1")])
    client = FakeClient(thread_pages=[page, page])

    stats.list_comments("vid_invalidate", client=client)
    stats.set_comment_moderation("c1", "rejected", client=client)
    stats.list_comments("vid_invalidate", client=client)

    # Cache was cleared by the moderation action, so the second list_comments
    # call had to hit the (fake) API again rather than serving stale data.
    assert len(client._threads.list_calls) == 2
