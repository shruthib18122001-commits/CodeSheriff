from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/github/login")
def github_login():
    """Returns the GitHub OAuth URL the frontend should redirect the user to."""
    params = (
        f"client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=repo read:user"
    )
    return {"auth_url": f"{GITHUB_AUTHORIZE_URL}?{params}"}


@router.get("/github/callback")
async def github_callback(code: str, db: Session = Depends(get_db)):
    """
    GitHub redirects here after the user approves access. We exchange the
    temporary `code` for an access token, fetch the user's GitHub profile,
    then upsert a local User row and issue our own JWT.
    """
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="GitHub token exchange failed")

        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        gh_user = user_resp.json()

    user = db.query(User).filter(User.github_id == str(gh_user["id"])).first()
    if not user:
        user = User(
            github_id=str(gh_user["id"]),
            github_username=gh_user["login"],
            email=gh_user.get("email"),
            avatar_url=gh_user.get("avatar_url"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = _create_jwt(str(user.id))

    # GitHub redirects the browser to *this* backend URL, not to the SPA --
    # so the SPA's /callback page can only receive the token by us
    # redirecting the browser onward with it in the query string.
    return RedirectResponse(url=f"{settings.frontend_base_url}/callback?token={jwt_token}")


def _create_jwt(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
