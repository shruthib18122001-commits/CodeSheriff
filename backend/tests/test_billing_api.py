import asyncio
from unittest.mock import MagicMock

import pytest
import stripe as stripe_sdk
from fastapi import HTTPException

from app.api import billing as billing_api
from app.api.billing import CheckoutRequest, create_checkout_session, stripe_webhook


class FakeRequest:
    """Minimal stand-in for starlette.Request -- only what stripe_webhook reads."""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self):
        return self._body


def test_create_checkout_session_success(make_user, monkeypatch):
    user = make_user()
    monkeypatch.setattr(billing_api, "PLAN_PRICE_IDS", {"pro": "price_123", "team": "price_456"})

    fake_session = MagicMock(url="https://checkout.stripe.com/session/abc")
    monkeypatch.setattr(billing_api.stripe.checkout.Session, "create", lambda **kwargs: fake_session)

    result = create_checkout_session(CheckoutRequest(plan="pro"), current_user=user)

    assert result.checkout_url == "https://checkout.stripe.com/session/abc"


def test_create_checkout_session_unknown_plan(make_user):
    user = make_user()
    with pytest.raises(HTTPException) as exc_info:
        create_checkout_session(CheckoutRequest(plan="enterprise"), current_user=user)
    assert exc_info.value.status_code == 400


def test_create_checkout_session_400_when_price_not_configured(make_user, monkeypatch):
    user = make_user()
    monkeypatch.setattr(billing_api, "PLAN_PRICE_IDS", {"pro": "", "team": ""})

    with pytest.raises(HTTPException) as exc_info:
        create_checkout_session(CheckoutRequest(plan="pro"), current_user=user)
    assert exc_info.value.status_code == 400


def test_create_checkout_session_502_on_stripe_error(make_user, monkeypatch):
    user = make_user()
    monkeypatch.setattr(billing_api, "PLAN_PRICE_IDS", {"pro": "price_123", "team": "price_456"})

    def boom(**kwargs):
        raise stripe_sdk.error.StripeError("stripe is down")

    monkeypatch.setattr(billing_api.stripe.checkout.Session, "create", boom)

    with pytest.raises(HTTPException) as exc_info:
        create_checkout_session(CheckoutRequest(plan="pro"), current_user=user)
    assert exc_info.value.status_code == 502


def test_webhook_rejects_invalid_signature(fake_db, monkeypatch):
    def boom(payload, sig_header, secret):
        raise stripe_sdk.error.SignatureVerificationError("bad signature", "sig_header")

    monkeypatch.setattr(billing_api.stripe.Webhook, "construct_event", boom)
    request = FakeRequest(body=b"{}", headers={"stripe-signature": "bad"})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(stripe_webhook(request, db=fake_db))
    assert exc_info.value.status_code == 400


def test_webhook_updates_user_plan_on_checkout_completed(make_user, fake_db, monkeypatch):
    user = make_user(plan="free")
    fake_db.query.return_value.filter.return_value.first.return_value = user

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"user_id": str(user.id), "plan": "pro"},
                "customer": "cus_123",
            }
        },
    }
    monkeypatch.setattr(billing_api.stripe.Webhook, "construct_event", lambda *a, **kw: fake_event)

    request = FakeRequest(body=b"{}", headers={"stripe-signature": "valid"})
    result = asyncio.run(stripe_webhook(request, db=fake_db))

    assert result == {"received": True}
    assert user.plan == "pro"
    assert user.stripe_customer_id == "cus_123"
    fake_db.commit.assert_called_once()


def test_webhook_ignores_unhandled_event_types(fake_db, monkeypatch):
    fake_event = {"type": "invoice.paid", "data": {"object": {}}}
    monkeypatch.setattr(billing_api.stripe.Webhook, "construct_event", lambda *a, **kw: fake_event)

    request = FakeRequest(body=b"{}", headers={"stripe-signature": "valid"})
    result = asyncio.run(stripe_webhook(request, db=fake_db))

    assert result == {"received": True}
    fake_db.commit.assert_not_called()


def test_webhook_handles_missing_user_gracefully(fake_db, monkeypatch):
    fake_db.query.return_value.filter.return_value.first.return_value = None
    fake_event = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"user_id": "does-not-exist", "plan": "pro"}, "customer": "cus_123"}},
    }
    monkeypatch.setattr(billing_api.stripe.Webhook, "construct_event", lambda *a, **kw: fake_event)

    request = FakeRequest(body=b"{}", headers={"stripe-signature": "valid"})
    result = asyncio.run(stripe_webhook(request, db=fake_db))

    assert result == {"received": True}
    fake_db.commit.assert_not_called()
