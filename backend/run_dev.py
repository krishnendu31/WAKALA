"""Start the WAKALA backend in local development mode.

Enables the predefined developer demonstration endpoints (/api/dev/*) and
binds to 127.0.0.1 only. Equivalent to:

    WAKALA_DEV_MODE=1 uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import os

import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("WAKALA_DEV_MODE", "1")
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("WAKALA_PORT", "8000")), reload=False)
