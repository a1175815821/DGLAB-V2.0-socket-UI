"""DGLAB V2.0 Socket — launch local control UI."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    import uvicorn
    from api import app

    host = "127.0.0.1"
    port = 8787
    print(f"DGLAB Control UI -> http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
