"""Authentication.

Off by default because the common case is localhost, where it adds nothing.
It exists so the dashboard can be reached from a phone without leaving an
unauthenticated, fully writable page open to whoever finds the port.
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(conn, cfg, monkeypatch):
    monkeypatch.setenv("CADRE_DATA", str(cfg.data_dir))
    monkeypatch.setenv("CADRE_DB", str(cfg.db_path))
    monkeypatch.setenv("CADRE_ARCHIVE", str(cfg.archive_dir))
    from cadre.web.app import app
    return TestClient(app)


def _auth(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_password_set_means_no_auth(app_client, monkeypatch):
    monkeypatch.delenv("CADRE_PASSWORD", raising=False)
    assert app_client.get("/").status_code == 200


def test_password_set_rejects_anonymous(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    response = app_client.get("/")
    assert response.status_code == 401
    assert "Basic" in response.headers["www-authenticate"]


def test_correct_credentials_pass(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    assert app_client.get("/", headers=_auth("cadre", "hunter2")).status_code == 200


def test_wrong_password_rejected(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    assert app_client.get("/", headers=_auth("cadre", "wrong")).status_code == 401


def test_wrong_user_rejected(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    assert app_client.get("/", headers=_auth("someone", "hunter2")).status_code == 401


def test_custom_username(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    monkeypatch.setenv("CADRE_USER", "tom")
    assert app_client.get("/", headers=_auth("tom", "hunter2")).status_code == 200
    assert app_client.get("/", headers=_auth("cadre", "hunter2")).status_code == 401


def test_write_endpoints_are_protected_too(app_client, conn, monkeypatch):
    """The review controls are unconfirmed POSTs -- an unprotected instance is
    writable, not merely readable."""
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    conn.execute(
        """INSERT INTO event (kind, first_seen_at, last_seen_at, significance)
           VALUES ('investigation_opened', datetime('now'), datetime('now'), 1.0)"""
    )
    conn.commit()
    event_id = conn.execute("SELECT id FROM event LIMIT 1").fetchone()["id"]
    response = app_client.post(f"/event/{event_id}/state",
                               data={"state": "dismissed"}, follow_redirects=False)
    assert response.status_code == 401


def test_malformed_authorization_header_is_rejected(app_client, monkeypatch):
    monkeypatch.setenv("CADRE_PASSWORD", "hunter2")
    for header in ({"Authorization": "Basic !!!not-base64!!!"},
                   {"Authorization": "Bearer token"},
                   {"Authorization": "Basic "}):
        assert app_client.get("/", headers=header).status_code == 401


def test_serve_refuses_public_bind_without_a_password(monkeypatch, capsys):
    from cadre.cli import main
    monkeypatch.delenv("CADRE_PASSWORD", raising=False)
    assert main(["serve", "--host", "0.0.0.0"]) == 2
    assert "refusing to bind" in capsys.readouterr().err
