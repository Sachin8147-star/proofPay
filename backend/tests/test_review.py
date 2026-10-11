from app.review import review


def ms(*reqs, **kw):
    return [{"title": "M", "requirements": [{"hidden": False, **r} for r in reqs], **kw}]


def kinds(issues): return [(i["requirement"], i["severity"]) for i in issues]


def test_sound_contract_has_no_issues():
    out = review(ms({"title": "Products endpoint lists items", "kind": "http", "spec": {"path": "/api/products", "expect_status": 200, "expect_contains": "id"}},
                    {"title": "Unit tests pass", "kind": "command", "spec": {"cmd": "pytest -q"}}))
    assert out == []


def test_vague_wording_on_file_check_warns():
    out = review(ms({"title": "Make the site look modern", "kind": "file_exists", "spec": {"path": "style.css"}}))
    assert any(i["severity"] == "warn" and "modern" in i["issue"] for i in out)


def test_vague_wording_on_real_test_is_info():
    out = review(ms({"title": "Fast search", "kind": "command", "spec": {"cmd": "pytest -q"}}))
    assert kinds(out) == [(0, "info")]


def test_behavior_claim_with_file_check_warns():
    out = review(ms({"title": "Login works", "kind": "file_contains", "spec": {"path": "auth.py", "pattern": "def login"}}))
    assert any("file check cannot prove" in i["issue"] for i in out)


pytest_cmds = ["true", "exit 0", "echo ok", "ls", "pytest || true", "npm test; true"]


def test_always_succeeding_commands_warn():
    for cmd in pytest_cmds:
        out = review(ms({"title": "Tests pass", "kind": "command", "spec": {"cmd": cmd}}))
        assert any("always succeeds" in i["issue"] for i in out), cmd


def test_loose_pattern_and_home_page_only():
    out = review(ms({"title": "Has code", "kind": "file_contains", "spec": {"path": "a.py", "pattern": ".*"}},
                    {"title": "Site online", "kind": "http", "spec": {"path": "/", "expect_status": 200}}))
    assert {i["requirement"] for i in out} == {0, 1}


def test_server_error_expectation_and_invalid_spec():
    out = review(ms({"title": "Fails on purpose", "kind": "http", "spec": {"path": "/x", "expect_status": 500}},
                    {"title": "Bad path", "kind": "file_exists", "spec": {"path": "../etc/passwd"}}))
    assert any("server error" in i["issue"] for i in out) and any("not valid" in i["issue"] for i in out)


def test_all_hidden_and_files_only_and_duplicates():
    out = review(ms({"title": "A", "kind": "file_exists", "spec": {"path": "a"}, "hidden": True},
                    {"title": "a", "kind": "file_exists", "spec": {"path": "b"}, "hidden": True}))
    msgs = " ".join(i["issue"] for i in out)
    assert "hidden" in msgs and "only checks files" in msgs and "same title" in msgs


def test_warnings_sort_before_info():
    out = review(ms({"title": "Fast", "kind": "command", "spec": {"cmd": "pytest"}}, {"title": "x", "kind": "command", "spec": {"cmd": "true"}}))
    assert out[0]["severity"] == "warn"
