"""
Nyx Light — Računovođa: Main Entry Point

Pokreni s: python -m nyx_light.main
Ili:       uvicorn nyx_light.api.app:app --host 0.0.0.0 --port 7860
"""

import logging
import os
import sys
from pathlib import Path

# Setup logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "nyx_light.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("nyx_light")


def main():
    """Start Nyx Light server."""
    import uvicorn

    host = os.environ.get("NYX_HOST", "0.0.0.0")
    port = int(os.environ.get("NYX_PORT", "7860"))
    workers = int(os.environ.get("NYX_WORKERS", "1"))
    reload_flag = os.environ.get("NYX_DEV", "0") == "1"

    logger.info("🌙 Nyx Light — Računovođa")
    logger.info("   Host: %s:%d", host, port)
    logger.info("   Workers: %d", workers)
    logger.info("   Dev mode: %s", reload_flag)

    # Ensure data dirs exist
    for d in ["data/memory_db", "data/rag_db", "data/dpo_datasets",
              "data/models/lora", "data/laws", "data/exports",
              "data/backups", "data/logs", "data/incoming_laws",
              "data/uploads", "data/prompt_cache"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    uvicorn.run(
        "nyx_light.api.app:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload_flag,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
