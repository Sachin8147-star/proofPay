import pytest

from app import chain, verifier


def test_canonical_hash_is_order_independent():
    assert chain.sha256_hex(chain.canonical({"b": 1, "a": [2, 3]})) == chain.sha256_hex(chain.canonical({"a": [2, 3], "b": 1}))


def test_wei_roundtrip():
    assert chain.to_wei("1.5") == 1_500_000_000_000_000_000
    assert str(chain.from_wei(chain.to_wei("0.000001"))) == "0.000001"


@pytest.mark.parametrize("kind,spec", [("file_exists", {"path": "../etc/passwd"}), ("file_exists", {"path": "/abs"}),
                                       ("file_contains", {"path": "a", "pattern": "("}), ("http", {"path": "x"}),
                                       ("command", {"cmd": "ls", "image": "evil:latest"}), ("nope", {})])
def test_bad_specs_rejected(kind, spec):
    with pytest.raises((ValueError, Exception)):
        verifier.validate_spec(kind, spec)


def test_file_tests(tmp_path):
    (tmp_path / "README.md").write_text("# Hello\ndef login(): pass")
    assert verifier.run_test("file_exists", {"path": "README.md"}, tmp_path, None)[0]
    assert not verifier.run_test("file_exists", {"path": "missing"}, tmp_path, None)[0]
    assert verifier.run_test("file_contains", {"path": "README.md", "pattern": "def login"}, tmp_path, None)[0]
    assert not verifier.run_test("file_contains", {"path": "README.md", "pattern": "logout"}, tmp_path, None)[0]


def test_ssrf_guard():
    for bad in ("http://127.0.0.1:8000", "http://localhost", "http://169.254.169.254/latest", "ftp://example.com"):
        with pytest.raises(ValueError):
            verifier.safe_url(bad)


def test_repo_url_parsing():
    assert verifier.parse_repo("https://github.com/Sachin8147-star/QuickFolio.git") == ("Sachin8147-star", "QuickFolio")
    with pytest.raises(ValueError):
        verifier.parse_repo("https://evil.com/a/b")
