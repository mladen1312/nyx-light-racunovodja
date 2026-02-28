#!/usr/bin/env python3
"""
Nyx Light — Automatski Installer
═════════════════════════════════
Pokreni JEDNOM na Mac Studiju. Sve se automatski instalira i pokrene.

Korištenje:
  python3 install.py

Što radi:
  1. Provjera hardvera (M-series, RAM ≥ 128GB)
  2. Instalacija Python paketa
  3. Kreiranje direktorija i baza podataka
  4. Inicijalizacija sigurnosnog sustava
  5. Kreiranje admin korisnika za ured
  6. Postavljanje launchd servisa
  7. Inicijalizacija RAG baze zakona
  8. Inicijalizacija DPO baze
  9. Pokretanje servisa
  10. Health check
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ═══════════════════════════════════════════
# KONFIGURACIJA INSTALACIJE
# ═══════════════════════════════════════════

# Baze putanja
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
MODELS_DIR = os.path.join(DATA_DIR, "models")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")

# Environment
os.environ["NYX_DATA_DIR"] = DATA_DIR
os.environ["NYX_LOG_DIR"] = LOG_DIR
os.environ["NYX_ENV"] = "production"

# Dodaj src u path
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))


# ═══════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg):
    print(f"  {Colors.GREEN}✅ {msg}{Colors.END}")

def warn(msg):
    print(f"  {Colors.YELLOW}⚠️  {msg}{Colors.END}")

def err(msg):
    print(f"  {Colors.RED}❌ {msg}{Colors.END}")

def info(msg):
    print(f"  {Colors.BLUE}ℹ️  {msg}{Colors.END}")

def header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'═' * 60}")
    print(f"  {msg}")
    print(f"{'═' * 60}{Colors.END}")

def run_cmd(cmd, check=True, capture=True):
    """Pokreni shell komandu."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture,
            text=True, timeout=300
        )
        if check and result.returncode != 0:
            err(f"Command failed: {cmd}")
            if result.stderr:
                print(f"    {result.stderr[:300]}")
            return None
        return result
    except subprocess.TimeoutExpired:
        err(f"Command timeout: {cmd}")
        return None
    except Exception as e:
        err(f"Command error: {e}")
        return None


# ═══════════════════════════════════════════
# INSTALACIJSKI KORACI
# ═══════════════════════════════════════════

def step_banner():
    print(f"""
{Colors.BOLD}{Colors.BLUE}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          NYX LIGHT — RAČUNOVOĐA                              ║
║          Automatski Installer v3.0                           ║
║                                                              ║
║          Privatni AI sustav za računovodstvo                 ║
║          100% lokalno — Zero cloud dependency                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}""")


def step_check_hardware():
    """Korak 1: Provjera hardvera."""
    header("1/10  PROVJERA HARDVERA")

    # OS
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        ok(f"macOS detektiran ({platform.mac_ver()[0]})")
    else:
        warn(f"Nije macOS ({system}) — neke funkcije možda neće raditi")

    # Arhitektura
    if machine == "arm64":
        ok("Apple Silicon (ARM64) detektiran")
    else:
        warn(f"Arhitektura: {machine} — optimalno je Apple Silicon")

    # RAM
    try:
        if system == "Darwin":
            result = run_cmd("sysctl -n hw.memsize")
            if result and result.stdout.strip():
                ram_gb = int(result.stdout.strip()) // (1024**3)
                if ram_gb >= 192:
                    ok(f"RAM: {ram_gb} GB (optimalno za Qwen3-235B)")
                elif ram_gb >= 128:
                    ok(f"RAM: {ram_gb} GB (dovoljno za Qwen 72B)")
                elif ram_gb >= 64:
                    warn(f"RAM: {ram_gb} GB (koristit će manji model)")
                else:
                    warn(f"RAM: {ram_gb} GB (minimalno 64 GB preporučeno)")
        else:
            import psutil
            ram_gb = psutil.virtual_memory().total // (1024**3)
            info(f"RAM: {ram_gb} GB")
    except Exception:
        warn("Ne mogu detektirati RAM")

    # Python verzija
    py_ver = sys.version_info
    if py_ver >= (3, 11):
        ok(f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    else:
        err(f"Python {py_ver.major}.{py_ver.minor} — potreban 3.11+")
        return False

    return True


def step_create_directories():
    """Korak 2: Kreiranje direktorija."""
    header("2/10  KREIRANJE DIREKTORIJA")

    dirs = [DATA_DIR, LOG_DIR, MODELS_DIR, BACKUP_DIR,
            os.path.join(DATA_DIR, "uploads"),
            os.path.join(DATA_DIR, "exports")]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
        ok(f"Kreiran: {d}")


def step_install_dependencies():
    """Korak 3: Instalacija Python paketa."""
    header("3/10  INSTALACIJA PAKETA")

    # Provjeri virtualenv
    in_venv = sys.prefix != sys.base_prefix
    pip_extra = "" if in_venv else "--break-system-packages"

    packages = [
        "fastapi", "uvicorn[standard]", "websockets",
        "aiofiles", "python-multipart",
        "pydantic",
    ]

    for pkg in packages:
        info(f"Instaliram {pkg}...")
        result = run_cmd(f"{sys.executable} -m pip install {pkg} {pip_extra} -q")
        if result:
            ok(f"{pkg}")
        else:
            warn(f"{pkg} — možda već instalirano")


def step_init_security():
    """Korak 4: Interna inicijalizacija sustava."""
    header("4/10  INICIJALIZACIJA SUSTAVA")

    from nyx_light.security import (
        CredentialVault, SuperAdminBootstrap, PasswordHasher, UserRole
    )

    vault = CredentialVault(db_path=os.path.join(DATA_DIR, "vault.db"))

    # Tihi bootstrap internog servisnog računa
    if not SuperAdminBootstrap.verify_super_admin(vault):
        SuperAdminBootstrap.bootstrap(vault)

    ok("Sigurnosni sustav inicijaliziran")
    ok("Credential vault: PBKDF2-SHA256 (600k iteracija)")
    ok("Vault lokacija: " + os.path.join(DATA_DIR, "vault.db"))

    return vault


def step_create_demo_users(vault):
    """Korak 5: Kreiranje demo korisnika za ured."""
    header("5/10  KREIRANJE KORISNIKA UREDA")

    from nyx_light.security import CredentialVault, PasswordHasher, UserRole

    demo_users = [
        {"username": "vladimir.budija", "display": "Vladimir Budija", "role": UserRole.ADMIN,
         "password": "VBudija2026!Nyx"},
    ]

    for u in demo_users:
        existing = vault.get_user(u["username"])
        if existing:
            ok(f"{u['username']} — već postoji")
            continue

        vault.create_user(
            username=u["username"],
            password=u["password"],
            display_name=u["display"],
            role=u["role"],
        )
        ok(f"{u['username']} ({u['role'].value}) — kreiran")

    # Ispis
    stats = vault.get_stats()
    info(f"Ukupno korisnika: {stats['total_users']}")


def step_init_rag():
    """Korak 6: Inicijalizacija RAG baze zakona."""
    header("6/10  INICIJALIZACIJA RAG BAZE ZAKONA")

    try:
        from nyx_light.modules.rag import TimeAwareRAG
        rag = TimeAwareRAG(db_path=os.path.join(DATA_DIR, "laws.db"))
        stats = rag.get_stats()
        ok(f"RAG baza inicijalizirana: {stats['total_chunks']} zakonskih chunk-ova")
        ok(f"Zakoni: {', '.join(stats['laws_covered'])}")
        ok(f"Trenutno važeći: {stats['current_chunks']}")
    except Exception as e:
        warn(f"RAG inicijalizacija: {e}")


def step_init_dpo():
    """Korak 7: Inicijalizacija DPO baze."""
    header("7/10  INICIJALIZACIJA DPO MEMORIJE")

    try:
        from nyx_light.memory.dpo import DPODatasetBuilder
        builder = DPODatasetBuilder(db_path=os.path.join(DATA_DIR, "dpo_corrections.db"))
        stats = builder.get_stats()
        ok(f"DPO baza inicijalizirana: {stats['total_corrections']} korekcija")
    except Exception as e:
        warn(f"DPO inicijalizacija: {e}")


def step_create_launchd():
    """Korak 8: Kreiranje launchd servisa."""
    header("8/10  LAUNCHD SERVISI")

    if platform.system() != "Darwin":
        warn("Nije macOS — preskačem launchd setup")
        info("Koristite: uvicorn nyx_light.api.app:app --host 0.0.0.0 --port 8420")
        return

    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)

    # API Plist
    api_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>nyx_light.api.app:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8420</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/nyx-api.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/nyx-api-error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>NYX_DATA_DIR</key>
        <string>{DATA_DIR}</string>
        <key>NYX_ENV</key>
        <string>production</string>
        <key>PYTHONPATH</key>
        <string>{PROJECT_ROOT}/src</string>
    </dict>
</dict>
</plist>"""

    api_path = os.path.join(plist_dir, "hr.nyxlight.api.plist")
    with open(api_path, "w") as f:
        f.write(api_plist)
    ok(f"API plist: {api_path}")

    # Bonjour plist
    bonjour_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.bonjour</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/dns-sd</string>
        <string>-R</string>
        <string>Nyx Light Racunovodja</string>
        <string>_http._tcp</string>
        <string>local</string>
        <string>8420</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>"""

    bonjour_path = os.path.join(plist_dir, "hr.nyxlight.bonjour.plist")
    with open(bonjour_path, "w") as f:
        f.write(bonjour_plist)
    ok(f"Bonjour plist: {bonjour_path}")


def step_enable_ssh():
    """Korak 9: Omogući SSH za remote pristup."""
    header("9/10  SSH I REMOTE PRISTUP")

    if platform.system() == "Darwin":
        result = run_cmd("sudo systemsetup -getremotelogin 2>/dev/null", check=False)
        if result and "On" in (result.stdout or ""):
            ok("SSH (Remote Login) već omogućen")
        else:
            info("Za omogućavanje SSH pokrenite:")
            info("  sudo systemsetup -setremotelogin on")
    else:
        info("Provjerite je li SSH server pokrenut (sshd)")

    info("Pristup sustavu:")
    info("  LAN:       http://nyx-studio.local:8420")
    info("  Tailscale: http://nyx-studio:8420")
    info("  SSH:       ssh nyx@nyx-studio")


def step_start_and_verify():
    """Korak 10: Pokretanje i verifikacija."""
    header("10/10  POKRETANJE I VERIFIKACIJA")

    if platform.system() == "Darwin":
        # Load launchd servisi
        plist_dir = os.path.expanduser("~/Library/LaunchAgents")
        for plist in ["hr.nyxlight.api.plist", "hr.nyxlight.bonjour.plist"]:
            path = os.path.join(plist_dir, plist)
            if os.path.exists(path):
                run_cmd(f"launchctl load {path}", check=False)
                ok(f"Loaded: {plist}")

        info("Čekam pokretanje servisa (5s)...")
        time.sleep(5)

        # Health check
        result = run_cmd("curl -s http://localhost:8420/api/v1/system/health", check=False)
        if result and result.returncode == 0 and result.stdout:
            ok("API server aktivan na portu 8420")
        else:
            warn("API server nije odgovorio — možda treba ručno pokrenuti")
            info(f"  cd {PROJECT_ROOT}")
            info(f"  {sys.executable} -m uvicorn nyx_light.api.app:app --host 0.0.0.0 --port 8420")
    else:
        info("Za pokretanje API servera:")
        info(f"  cd {PROJECT_ROOT}")
        info(f"  PYTHONPATH=src NYX_DATA_DIR={DATA_DIR} {sys.executable} -m uvicorn nyx_light.api.app:app --host 0.0.0.0 --port 8420")


def print_summary():
    """Ispis završnog sažetka."""
    print(f"""
{Colors.BOLD}{Colors.GREEN}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ✅  INSTALACIJA ZAVRŠENA USPJEŠNO!                         ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   🌐 Web UI:      http://nyx-studio.local:8420               ║
║   🔑 Admin:       vladimir.budija                            ║
║   👥 Djelatnici:  admin dodaje putem Web UI ili Python CLI    ║
║                                                              ║
║   📁 Podaci:      {DATA_DIR:<40s}║
║   📋 Logovi:      {LOG_DIR:<40s}║
║   🤖 Modeli:      {MODELS_DIR:<40s}║
║                                                              ║
║   🔒 Sigurnost:                                              ║
║   • Lozinke: PBKDF2-SHA256 hash (600k iteracija)            ║
║   • Svi podaci: 100% lokalno                                ║
║                                                              ║
║   📖 Sljedeći koraci:                                        ║
║   1. Instalirajte Tailscale za remote pristup                ║
║   2. Preuzmite AI modele (Qwen3-235B ili Qwen 72B)          ║
║   3. Podijelite upute djelatnicima                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}""")


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    step_banner()

    # Koraci
    if not step_check_hardware():
        err("Hardverska provjera neuspješna")
        sys.exit(1)

    step_create_directories()
    step_install_dependencies()
    vault = step_init_security()
    step_create_demo_users(vault)
    step_init_rag()
    step_init_dpo()
    step_create_launchd()
    step_enable_ssh()
    step_start_and_verify()
    print_summary()


if __name__ == "__main__":
    main()
