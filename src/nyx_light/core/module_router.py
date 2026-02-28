"""
Nyx Light — Module Router (PROXY)

Ovaj modul je PROXY na glavni router u nyx_light.router.
Zadržan za backward compatibility — sav kod je u nyx_light/router/__init__.py

MIGRACIJA: Umjesto `from nyx_light.core.module_router import ModuleRouter`
           koristite `from nyx_light.router import ModuleRouter`
"""

# Re-export sve iz glavnog routera
from nyx_light.router import ModuleRouter, RouteResult, INTENT_PATTERNS  # noqa: F401

__all__ = ["ModuleRouter", "RouteResult", "INTENT_PATTERNS"]
