import pytest

from services.file_validation import verify_file_signature
from tools.sql_tool import validate_sql_query


@pytest.mark.parametrize("query", [
    "DROP TABLE documents",
    "SELECT 1; DROP TABLE users",
    "SELECT username, hashed_password FROM users",
    "SELECT * FROM public.chat_history",
    "DELETE FROM chat_history",
])
def test_dangerous_sql_is_rejected(query):
    ok, _ = validate_sql_query(query)
    assert not ok


def test_allowed_sql_passes():
    ok, msg = validate_sql_query("SELECT COUNT(DISTINCT filename) FROM documents WHERE created_at > NOW() - INTERVAL '1 day'")
    assert ok, msg


def test_file_signature_must_match_extension():
    assert verify_file_signature(b"%PDF-1.7 ...", ".pdf")
    assert not verify_file_signature(b"ini teks biasa", ".pdf")
    assert not verify_file_signature(b"MZ\x90\x00", ".png")
