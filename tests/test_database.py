import time

import pytest

from app.database import ChatDatabase, suggest_title
from app.formatting import segment_message, strip_reasoning


@pytest.fixture
def db(paths):
    d = ChatDatabase(paths.database)
    yield d
    d.close()


def test_create_and_list_conversations(db):
    a = db.create_conversation("First")
    time.sleep(0.01)
    b = db.create_conversation("Second")
    ids = [c.id for c in db.list_conversations()]
    assert ids == [b.id, a.id]  # most recent first


def test_messages_round_trip_and_touch_conversation(db):
    conv = db.create_conversation("Chat")
    before = db.get_conversation(conv.id).updated_at
    time.sleep(0.01)
    db.add_message(conv.id, "user", "Hello")
    m = db.add_message(conv.id, "assistant", "Hi!", "smollm2-360m-instruct", {"tokens": 2})
    msgs = db.messages(conv.id)
    assert [(x.role, x.content) for x in msgs] == [("user", "Hello"), ("assistant", "Hi!")]
    assert msgs[1].metadata == {"tokens": 2}
    assert msgs[1].model_id == "smollm2-360m-instruct"
    assert db.get_conversation(conv.id).updated_at > before

    db.update_message(m.id, "Hi there!", metadata={"tokens": 3})
    assert db.messages(conv.id)[1].content == "Hi there!"
    db.delete_message(m.id)
    assert db.count_messages(conv.id) == 1


def test_rename_model_selection_and_delete_cascade(db):
    conv = db.create_conversation("Old")
    db.add_message(conv.id, "user", "x")
    db.rename_conversation(conv.id, "  New   title ")
    db.set_conversation_model(conv.id, "smollm3-3b", "manual")
    got = db.get_conversation(conv.id)
    assert got.title == "New title"
    assert (got.model_id, got.model_mode) == ("smollm3-3b", "manual")
    assert got.title_is_auto is False
    with pytest.raises(ValueError):
        db.set_conversation_model(conv.id, "", "bogus")
    db.delete_conversation(conv.id)
    assert db.get_conversation(conv.id) is None
    assert db.messages(conv.id) == []


def test_search_matches_titles_and_message_text(db):
    a = db.create_conversation("Cooking ideas")
    b = db.create_conversation("Work")
    db.add_message(b.id, "user", "Explain 100% of the regex_magic")
    assert [c.id for c in db.list_conversations("cook")] == [a.id]
    assert [c.id for c in db.list_conversations("regex_magic")] == [b.id]
    assert [c.id for c in db.list_conversations("100%")] == [b.id]
    assert db.list_conversations("nothing-here") == []


def test_persists_across_reopen(paths):
    d1 = ChatDatabase(paths.database)
    conv = d1.create_conversation("Persisted", "smollm2-135m-instruct", "manual")
    d1.add_message(conv.id, "user", "remember me")
    d1.close()
    d2 = ChatDatabase(paths.database)
    got = d2.get_conversation(conv.id)
    assert got.model_mode == "manual" and got.model_id == "smollm2-135m-instruct"
    assert d2.messages(conv.id)[0].content == "remember me"
    d2.close()


def test_suggest_title():
    assert suggest_title("what is the capital of France? And why?") == "What is the capital of France?"
    long = suggest_title("please write a very long story about a dragon who learns to code in rust")
    assert len(long) <= 49 and long.endswith("…")
    assert suggest_title("   ") == "New chat"


def test_segment_message_code_and_thinking():
    text = "<think>plan it</think>Here:\n```python\ndef f():\n    return 1\n```\nDone."
    segs = segment_message(text)
    assert [s["kind"] for s in segs] == ["think", "text", "code", "text"]
    assert segs[2]["lang"] == "python" and "def" in segs[2]["html"]
    assert segs[0]["open"] is False
    # streaming: unterminated code fence and think block
    assert segment_message("```js\nlet x")[-1]["open"] is True
    assert segment_message("<think>still going")[0]["open"] is True
    assert strip_reasoning("<think>a</think>answer") == "answer"
