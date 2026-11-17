from src.pipeline import sha256

def test_sha256_is_deterministic():
    assert sha256(b"abc") == sha256(b"abc")

def test_sha256_changes_when_content_changes():
    assert sha256(b"abc") != sha256(b"abcd")
