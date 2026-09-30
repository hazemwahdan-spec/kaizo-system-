"""Vercel deployment adapter for KAIZO P05.

The P05 application logic remains in longitudinal/main.py. This file only
exports the existing FastAPI app through Vercel's recognized FastAPI entrypoint.
"""
from longitudinal.main import app

__all__ = ["app"]
