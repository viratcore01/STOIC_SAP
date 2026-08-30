"""Vercel Serverless Function entrypoint — exports the CCRO Demo Backend FastAPI app.

Vercel looks for ASGI apps in api/*.py, and this file re-exports the `app`
object from the demo backend so that Vercel's Python runtime picks it up.
"""
from demo.backend.main import app  # noqa: F401
