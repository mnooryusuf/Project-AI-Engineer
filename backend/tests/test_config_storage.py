import os
import time

import pytest

import config
from services import document_service


def _settings(**overrides):
    base = dict(
        secret_key="x" * 40,
        database_url="postgresql://postgres:kuat@localhost:5432/db",
        database_url_readonly="postgresql://ro:kuat@localhost:5432/db",
    )
    return config.Settings(**{**base, **overrides})


def test_example_secret_key_blocks_production():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config._check_secrets(_settings(app_env="production", secret_key=config.EXAMPLE_SECRET_KEY))


def test_example_db_password_blocks_production():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        config._check_secrets(_settings(app_env="production", database_url="postgresql://postgres:mysecretpassword@h/db"))


def test_example_secrets_only_warn_in_development(capsys):
    config._check_secrets(_settings(app_env="development", secret_key=config.EXAMPLE_SECRET_KEY))
    assert "PERINGATAN" in capsys.readouterr().err


def test_strong_secrets_pass_in_production():
    config._check_secrets(_settings(app_env="production"))


def test_stored_files_for_matches_only_that_document(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service.settings, "upload_dir", str(tmp_path))
    old = tmp_path / ("a" * 32 + "_surat.pdf")
    new = tmp_path / ("b" * 32 + "_surat.pdf")
    other = tmp_path / ("c" * 32 + "_surat.pdf.bak")
    plain = tmp_path / "surat.pdf"
    for f in (old, new, other, plain):
        f.write_bytes(b"x")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert document_service.stored_files_for("surat.pdf") == [old, new]
