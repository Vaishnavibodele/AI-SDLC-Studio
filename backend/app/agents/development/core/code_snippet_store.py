from typing import Dict

class CodeSnippetStore:
    def __init__(self):
        self.snippets: Dict[str, str] = {
            "fastapi_cors": """
# Standard CORS config
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
""",
            "sqlalchemy_session": """
# Standard DB Session generator
from sqlalchemy.orm import Session
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
""",
            "jwt_auth": """
# Standard JWT Token parser
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = "secret_key_jwt_placeholder"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token username credentials")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate token credentials")
"""
        }

    def get_snippet(self, name: str) -> str:
        return self.snippets.get(name, "")

code_snippet_store = CodeSnippetStore()
