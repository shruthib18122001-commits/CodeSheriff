import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = settings.stripe_secret_key

PLAN_PRICE_IDS = {
    "pro": settings.stripe_price_pro,
    "team": settings.stripe_price_team,
}


class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "team"


class CheckoutResponse(BaseModel):
    checkout_url: str


@router.get("/plan")
def get_plan(current_user: User = Depends(get_current_user)):
    return {
        "plan": current_user.plan,
        "queries_this_month": current_user.queries_this_month,
    }


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Creates a Stripe Checkout session for upgrading from free -> pro/team."""
    price_id = PLAN_PRICE_IDS.get(payload.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.plan}'")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=current_user.email or None,
            client_reference_id=str(current_user.id),
            success_url=f"{settings.frontend_base_url}/dashboard?checkout=success",
            cancel_url=f"{settings.frontend_base_url}/dashboard?checkout=cancelled",
            metadata={"user_id": str(current_user.id), "plan": payload.plan},
        )
    except stripe.error.StripeError as e:
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(status_code=502, detail="Could not start checkout") from e

    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Called by Stripe's servers -- deliberately NOT behind get_current_user,
    since Stripe can't present a CodeSheriff JWT. Authenticity is instead
    verified via the `Stripe-Signature` header against STRIPE_WEBHOOK_SECRET.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except ValueError:
        logger.warning("Rejected Stripe webhook with unparseable payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.warning("Rejected Stripe webhook with invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        _handle_checkout_completed(event["data"]["object"], db)

    return {"received": True}


def _handle_checkout_completed(session: dict, db: Session) -> None:
    user_id = (session.get("metadata") or {}).get("user_id") or session.get("client_reference_id")
    plan = (session.get("metadata") or {}).get("plan")
    customer_id = session.get("customer")

    if not user_id or not plan:
        logger.warning("checkout.session.completed missing user_id/plan in metadata")
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning("Stripe webhook referenced unknown user_id=%s", user_id)
        return

    user.plan = plan
    if customer_id:
        user.stripe_customer_id = customer_id
    db.commit()
