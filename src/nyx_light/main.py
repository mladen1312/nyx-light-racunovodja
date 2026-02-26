#!/usr/bin/env python3
"""
Nyx Light — Računovođa: Main Entry Point

Pokreće FastAPI server s vllm-mlx inference engineom
za 15 paralelnih korisnika na Mac Studio M5 Ultra.

Usage:
    python -m nyx_light.main
    python -m nyx_light.main --host 0.0.0.0 --port 8000
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nyx_light")


def main():
    parser = argparse.ArgumentParser(description="Nyx Light — Računovođa")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--workers", type=int, default=1, help="Uvicorn workers")
    parser.add_argument("--reload", action="store_true", help="Auto-reload for dev")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("═" * 60)
    logger.info("  🌙 Nyx Light — Računovođa v1.0.0")
    logger.info("  Privatni AI sustav za računovodstvo RH")
    logger.info("  © 2026 Dr. Mladen Mešter | Nexellum Lab d.o.o.")
    logger.info("═" * 60)

    try:
        import uvicorn
        uvicorn.run(
            "nyx_light.api.app:app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            reload=args.reload,
            log_level="debug" if args.debug else "info",
        )
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
