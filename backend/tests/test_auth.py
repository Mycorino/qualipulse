"""Tests for /auth endpoints."""
import pytest


SIGNUP_PAYLOAD = {"name": "Acme Inc", "email": "acme@example.com", "password": "Secure123!"}


class TestSignup:
    def test_signup_returns_tokens(self, client):
        resp = client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_signup_duplicate_email_returns_409(self, client):
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        resp = client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        assert resp.status_code == 409

    def test_signup_creates_unverified_account(self, client, db_session):
        from app.models.company import Company
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        company = db_session.query(Company).filter(Company.email == SIGNUP_PAYLOAD["email"]).first()
        assert company is not None
        assert company.email_verified is False

    def test_signup_creates_verification_token(self, client, db_session):
        from app.models.company import Company, EmailVerificationToken
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        company = db_session.query(Company).filter(Company.email == SIGNUP_PAYLOAD["email"]).first()
        token = db_session.query(EmailVerificationToken).filter(
            EmailVerificationToken.company_id == company.id
        ).first()
        assert token is not None
        assert token.used is False


class TestLogin:
    def test_login_valid_credentials(self, client):
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        resp = client.post("/auth/login", json={"email": SIGNUP_PAYLOAD["email"], "password": SIGNUP_PAYLOAD["password"]})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password_returns_401(self, client):
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        resp = client.post("/auth/login", json={"email": SIGNUP_PAYLOAD["email"], "password": "wrongpassword"})
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, client):
        resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "anything"})
        assert resp.status_code == 401


class TestTokenRefresh:
    def test_refresh_returns_new_tokens(self, client, registered_company):
        refresh_token = registered_company["tokens"]["refresh_token"]
        resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_invalid_token_returns_401(self, client):
        resp = client.post("/auth/refresh", json={"refresh_token": "not-a-valid-token"})
        assert resp.status_code == 401


class TestGetMe:
    def test_get_me_returns_profile(self, client, auth_headers, registered_company):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == registered_company["email"]
        assert "email_verified" in data

    def test_get_me_without_token_returns_401(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401


class TestEmailVerification:
    def test_verify_email_marks_account_verified(self, client, db_session):
        from app.models.company import Company, EmailVerificationToken
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        company = db_session.query(Company).filter(Company.email == SIGNUP_PAYLOAD["email"]).first()
        token = db_session.query(EmailVerificationToken).filter(
            EmailVerificationToken.company_id == company.id
        ).first()

        resp = client.post(f"/auth/verify-email?token={token.token}")
        assert resp.status_code == 200

        db_session.refresh(company)
        assert company.email_verified is True

    def test_verify_email_invalid_token_returns_400(self, client):
        resp = client.post("/auth/verify-email?token=invalid-token-xyz")
        assert resp.status_code == 400

    def test_verify_email_used_token_returns_400(self, client, db_session):
        from app.models.company import Company, EmailVerificationToken
        client.post("/auth/signup", json=SIGNUP_PAYLOAD)
        company = db_session.query(Company).filter(Company.email == SIGNUP_PAYLOAD["email"]).first()
        token = db_session.query(EmailVerificationToken).filter(
            EmailVerificationToken.company_id == company.id
        ).first()

        client.post(f"/auth/verify-email?token={token.token}")
        # Second use
        resp = client.post(f"/auth/verify-email?token={token.token}")
        assert resp.status_code == 400


class TestPasswordReset:
    def test_reset_request_always_returns_200(self, client):
        resp = client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
        assert resp.status_code == 200

    def test_confirm_invalid_token_returns_400(self, client):
        resp = client.post("/auth/password-reset/confirm", json={"token": "bad-token", "new_password": "NewPass123!"})
        assert resp.status_code == 400
