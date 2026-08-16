from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import FastAPI

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()

@app.post("/login")
@limiter.limit("5/minute")
def login():
    return {"msg": "login attempt"}
