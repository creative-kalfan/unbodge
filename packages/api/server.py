"""ASGI entrypoint for deployment (Phase 4). Run with uvicorn."""

from __future__ import annotations

from api import create_app

app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
