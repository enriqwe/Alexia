#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from flask import Flask, send_from_directory

from auth_core import AuthManager, init_user_from_cli


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "facturas-repository"

app = Flask(__name__)
auth = AuthManager(BASE_DIR, "Alexia")
auth.init_app(app)


@app.get("/")
@auth.require_login
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:path>")
@auth.require_login
def static_files(path):
    return send_from_directory(WEB_DIR, path)


def main():
    if init_user_from_cli(auth, sys.argv):
        return
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
