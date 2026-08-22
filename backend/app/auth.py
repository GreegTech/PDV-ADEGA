import os, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()

def hash_password(password: str): return password_hash.hash(password)
def verify_password(password: str, hashed: str): return password_hash.verify(password, hashed)

def make_token(user: User):
    exp = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES","480")))
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, os.environ["SECRET_KEY"], algorithm="HS256")

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(creds.credentials, os.environ["SECRET_KEY"], algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        raise HTTPException(401, "Token inválido ou expirado")
    if not user or not user.active:
        raise HTTPException(401, "Usuário inválido")
    return user
