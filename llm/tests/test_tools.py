import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import custom_llm_server as srv  # noqa: E402


def _db(tmp_path):
    return srv.get_db(os.path.join(str(tmp_path), "test.db"))


def _user(text):
    return srv.UserMessage(role="user", content=text)


def test_log_message_records_and_confirms(tmp_path):
    conn = _db(tmp_path)
    reply = srv.run_agent_turn(conn, [_user("log this: buy milk")])
    assert "buy milk" in reply
    rows = conn.execute("SELECT text FROM messages").fetchall()
    assert rows == [("buy milk",)]


def test_log_message_without_colon_logs_full_text(tmp_path):
    conn = _db(tmp_path)
    srv.run_agent_turn(conn, [_user("please log groceries")])
    rows = conn.execute("SELECT text FROM messages").fetchall()
    assert rows == [("please log groceries",)]


def test_list_messages_reads_back(tmp_path):
    conn = _db(tmp_path)
    srv.run_agent_turn(conn, [_user("log this: buy milk")])
    srv.run_agent_turn(conn, [_user("log this: water the plants")])
    reply = srv.run_agent_turn(conn, [_user("list my notes")])
    assert "buy milk" in reply
    assert "water the plants" in reply


def test_recall_takes_precedence_over_log_trigger(tmp_path):
    conn = _db(tmp_path)
    srv.run_agent_turn(conn, [_user("log this: buy milk")])
    # "what I have noted" contains the log-trigger "note" but must READ BACK, not log.
    reply = srv.run_agent_turn(conn, [_user("tell me what I have noted")])
    assert "buy milk" in reply
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_list_when_empty(tmp_path):
    conn = _db(tmp_path)
    reply = srv.run_agent_turn(conn, [_user("list my notes")])
    assert "haven't logged" in reply.lower()


def test_non_tool_message_returns_guidance(tmp_path):
    conn = _db(tmp_path)
    reply = srv.run_agent_turn(conn, [_user("hello there")])
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert "log" in reply.lower()


def test_persistence_across_connections(tmp_path):
    # Simulate a process restart: write with one connection, read back with a
    # fresh connection to the same file. Proves messages survive (unlike the old
    # in-memory list).
    path = os.path.join(str(tmp_path), "persist.db")
    conn1 = srv.get_db(path)
    srv.run_agent_turn(conn1, [_user("log this: remember me")])
    conn1.close()
    conn2 = srv.get_db(path)
    reply = srv.run_agent_turn(conn2, [_user("list my notes")])
    assert "remember me" in reply
