#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from flask import Flask, redirect

from auth_core import AuthManager, init_user_from_cli


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "facturas-repository"

app = Flask(__name__)
auth = AuthManager(BASE_DIR, "Alexia")
auth.init_app(app)


def public_dashboard(path: str = "") -> str:
    base = os.environ.get("PUBLIC_DASHBOARD_URL", "https://enriqwe.es/facturas/").rstrip("/") + "/"
    return base + path.lstrip("/")


@app.get("/")
def index():
    return redirect(public_dashboard(), code=302)


@app.get("/<path:path>")
def static_files(path):
    return redirect(public_dashboard(path), code=302)


def main():
    if init_user_from_cli(auth, sys.argv):
        return
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
