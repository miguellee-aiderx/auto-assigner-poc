"""event_parser 모듈 테스트."""

from __future__ import annotations

from auto_assigner.event_parser import parse_event


def test_parse_issue_comment_lgtm(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    event = parse_event(payload, "issue_comment")
    assert event is not None
    assert event.repo_owner == "aiderx-corp"
    assert event.repo_name == "a2-adm"
    assert event.pr_number == 352
    assert event.actor == "claude"
    assert event.is_lgtm is True


def test_parse_issue_comment_non_lgtm(load_fixture):
    payload = load_fixture("non_lgtm_comment.json")
    event = parse_event(payload, "issue_comment")
    assert event is not None
    assert event.is_lgtm is False


def test_parse_non_pr_issue_comment():
    payload = {
        "action": "created",
        "issue": {"number": 1},
        "comment": {"user": {"login": "claude"}, "body": "LGTM"},
        "repository": {"full_name": "aiderx-corp/a2-adm"},
    }
    event = parse_event(payload, "issue_comment")
    assert event is None


def test_parse_unknown_event(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    event = parse_event(payload, "push")
    assert event is None
