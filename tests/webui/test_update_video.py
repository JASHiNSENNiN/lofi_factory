"""videos.update replaces whole parts: the panel's edit must not erase the
fields it doesn't show (schedule, made-for-kids, license)."""
from webui import stats


class _Req:
    def __init__(self, result=None, sink=None, body=None):
        self.result, self.sink, self.body = result, sink, body

    def execute(self):
        if self.sink is not None:
            self.sink.append(self.body)
        return self.result


class _Videos:
    def __init__(self, current):
        self.current, self.sent = current, []

    def list(self, **_):
        return _Req({"items": [self.current]})

    def update(self, part, body):
        return _Req(sink=self.sent, body=body)


class _YT:
    def __init__(self, current):
        self.v = _Videos(current)

    def videos(self):
        return self.v


def test_edit_keeps_schedule_and_declarations():
    yt = _YT({"snippet": {"title": "old", "defaultLanguage": "en", "channelId": "x"},
              "status": {"privacyStatus": "private", "publishAt": "2026-10-03T08:00:00Z",
                         "selfDeclaredMadeForKids": False, "license": "youtube"}})
    assert stats.update_video("vid", title="new", description="d", tags=["a"],
                              privacy="private", client=yt)
    body = yt.v.sent[0]
    assert body["status"]["publishAt"] == "2026-10-03T08:00:00Z"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["snippet"]["defaultLanguage"] == "en" and body["snippet"]["title"] == "new"
    assert "channelId" not in body["snippet"]            # read-only fields aren't sent


def test_making_a_scheduled_video_public_drops_its_schedule():
    yt = _YT({"snippet": {}, "status": {"privacyStatus": "private",
                                         "publishAt": "2026-10-03T08:00:00Z"}})
    stats.update_video("vid", title="t", description="", tags=[], privacy="public", client=yt)
    assert "publishAt" not in yt.v.sent[0]["status"]
