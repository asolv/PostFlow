from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.core.config import cors_origins

def setup_cors(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins() or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
