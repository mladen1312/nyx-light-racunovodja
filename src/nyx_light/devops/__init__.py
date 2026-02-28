"""
Nyx Light — Remote DevOps Toolkit
══════════════════════════════════
Omogućuje live programiranje i debugging AI sustava
direktno iz Claude okruženja putem SSH-a.

Workflow:
  1. Claude editira kod lokalno
  2. Push na GitHub
  3. SSH na Mac Studio → git pull → restart servisa
  4. Provjera logova i zdravlja sustava

Ili brži put:
  1. Claude editira kod → SCP direktno na Mac Studio
  2. SSH → restart specifičnog modula
  3. Tail logova u realnom vremenu
"""

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════
# KONFIGURACIJA KONEKCIJE
# ═══════════════════════════════════════════

class ServiceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    RESTARTING = "restarting"
    UNKNOWN = "unknown"


@dataclass
class MacStudioConnection:
    """Konfiguracija SSH konekcije na Mac Studio."""
    host: str = "nyx-studio"           # Hostname ili IP
    user: str = "nyx"                   # SSH korisnik
    port: int = 22                      # SSH port
    key_path: str = ""                  # Putanja do SSH ključa (opcionalno)
    project_path: str = "/opt/nyx-light-racunovodja"  # Lokacija koda na Mac Studiju
    venv_path: str = "/opt/nyx-light-racunovodja/.venv"
    log_dir: str = "/opt/nyx-light-racunovodja/logs"
    data_dir: str = "/opt/nyx-light-racunovodja/data"
    github_repo: str = "mladen1312/nyx-light-racunovodja"
    github_branch: str = "main"

    # Servisi
    api_port: int = 8420
    mlx_port: int = 8422

    @property
    def ssh_cmd(self) -> str:
        """Bazna SSH komanda."""
        parts = ["ssh", "-o", "StrictHostKeyChecking=no",
                 "-o", "ConnectTimeout=10"]
        if self.key_path:
            parts.extend(["-i", self.key_path])
        parts.extend(["-p", str(self.port), f"{self.user}@{self.host}"])
        return " ".join(parts)

    @property
    def scp_prefix(self) -> str:
        """Bazna SCP komanda."""
        parts = ["scp", "-o", "StrictHostKeyChecking=no"]
        if self.key_path:
            parts.extend(["-i", self.key_path])
        parts.extend(["-P", str(self.port)])
        return " ".join(parts)

    @property
    def remote_prefix(self) -> str:
        """SSH prefix za remote komande."""
        return f"{self.ssh_cmd}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "user": self.user,
            "port": self.port,
            "project_path": self.project_path,
            "api_port": self.api_port,
            "mlx_port": self.mlx_port,
        }


# ═══════════════════════════════════════════
# SSH EXECUTOR
# ═══════════════════════════════════════════

class RemoteExecutor:
    """
    Izvršava komande na Mac Studiju putem SSH-a.
    Koristi se iz Claude bash_tool-a.
    """

    def __init__(self, conn: MacStudioConnection = None):
        self.conn = conn or MacStudioConnection()
        self._history: List[Dict] = []

    def exec(self, command: str, timeout: int = 30,
             capture: bool = True) -> Dict[str, Any]:
        """Izvrši komandu na remote Mac Studiju."""
        full_cmd = f'{self.conn.ssh_cmd} {shlex.quote(command)}'

        start = time.time()
        try:
            result = subprocess.run(
                full_cmd, shell=True, capture_output=capture,
                text=True, timeout=timeout
            )
            elapsed = round(time.time() - start, 2)

            entry = {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout.strip() if capture else "",
                "stderr": result.stderr.strip() if capture else "",
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
                "success": result.returncode == 0,
            }
            self._history.append(entry)
            return entry

        except subprocess.TimeoutExpired:
            return {"command": command, "success": False,
                    "error": f"Timeout ({timeout}s)", "returncode": -1}
        except Exception as e:
            return {"command": command, "success": False,
                    "error": str(e), "returncode": -1}

    def exec_in_project(self, command: str, **kwargs) -> Dict[str, Any]:
        """Izvrši komandu u project direktoriju."""
        return self.exec(f"cd {self.conn.project_path} && {command}", **kwargs)

    def exec_in_venv(self, command: str, **kwargs) -> Dict[str, Any]:
        """Izvrši komandu u virtualnom okruženju."""
        venv_activate = f"source {self.conn.venv_path}/bin/activate"
        return self.exec(
            f"cd {self.conn.project_path} && {venv_activate} && {command}",
            **kwargs
        )

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """Upload datoteku na Mac Studio putem SCP."""
        remote_full = f"{self.conn.user}@{self.conn.host}:{remote_path}"
        cmd = f"{self.conn.scp_prefix} {shlex.quote(local_path)} {remote_full}"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                   text=True, timeout=60)
            return {
                "success": result.returncode == 0,
                "local": local_path,
                "remote": remote_path,
                "stderr": result.stderr.strip(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """Download datoteku s Mac Studija."""
        remote_full = f"{self.conn.user}@{self.conn.host}:{remote_path}"
        cmd = f"{self.conn.scp_prefix} {remote_full} {shlex.quote(local_path)}"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                   text=True, timeout=60)
            return {
                "success": result.returncode == 0,
                "remote": remote_path,
                "local": local_path,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        """Testiraj SSH konekciju."""
        result = self.exec("echo 'SSH_OK' && hostname && uname -m && sw_vers -productVersion 2>/dev/null || true")
        if result.get("success"):
            lines = result["stdout"].split("\n")
            return {
                "connected": True,
                "hostname": lines[1] if len(lines) > 1 else "unknown",
                "arch": lines[2] if len(lines) > 2 else "unknown",
                "macos_version": lines[3] if len(lines) > 3 else "unknown",
                "latency_ms": round(result["elapsed_seconds"] * 1000),
            }
        return {"connected": False, "error": result.get("error", result.get("stderr", "Unknown error"))}

    def get_history(self, last_n: int = 10) -> List[Dict]:
        return self._history[-last_n:]


# ═══════════════════════════════════════════
# SERVICE MANAGER
# ═══════════════════════════════════════════

class ServiceManager:
    """
    Upravlja Nyx Light servisima na Mac Studiju.

    Servisi:
      - nyx-api:  FastAPI server (:8420)
      - nyx-mlx:  MLX LLM server (:8422)
      - nyx-dpo:  Noćni DPO cron job
    """

    # launchd plist lokacije
    SERVICES = {
        "nyx-api": {
            "plist": "hr.nyxlight.api",
            "port": 8420,
            "health_url": "http://localhost:8420/api/v1/system/health",
            "description": "FastAPI Web/API server",
        },
        "nyx-mlx": {
            "plist": "hr.nyxlight.mlx",
            "port": 8422,
            "health_url": "http://localhost:8422/health",
            "description": "MLX LLM inference server",
        },
        "nyx-dpo": {
            "plist": "hr.nyxlight.dpo",
            "port": None,
            "description": "Nightly DPO optimizer (cron)",
        },
    }

    def __init__(self, executor: RemoteExecutor = None):
        self.executor = executor or RemoteExecutor()

    def status(self, service: str = None) -> Dict[str, Any]:
        """Status jednog ili svih servisa."""
        if service:
            return self._check_service(service)

        results = {}
        for svc_name in self.SERVICES:
            results[svc_name] = self._check_service(svc_name)
        return results

    def _check_service(self, service: str) -> Dict[str, Any]:
        """Provjeri status jednog servisa."""
        svc = self.SERVICES.get(service)
        if not svc:
            return {"error": f"Unknown service: {service}"}

        # Provjeri launchd
        result = self.executor.exec(
            f"launchctl list | grep {svc['plist']} || echo 'NOT_LOADED'"
        )

        if "NOT_LOADED" in result.get("stdout", ""):
            return {"service": service, "status": "stopped", "loaded": False}

        # Provjeri port
        status_info = {"service": service, "loaded": True}
        if svc["port"]:
            port_check = self.executor.exec(
                f"lsof -i :{svc['port']} -t 2>/dev/null | head -1"
            )
            pid = port_check.get("stdout", "").strip()
            if pid:
                status_info["status"] = "running"
                status_info["pid"] = int(pid)
                status_info["port"] = svc["port"]

                # Memory usage
                mem = self.executor.exec(f"ps -o rss= -p {pid}")
                if mem.get("success"):
                    rss_kb = int(mem["stdout"].strip() or "0")
                    status_info["memory_mb"] = round(rss_kb / 1024)
            else:
                status_info["status"] = "stopped"
        else:
            status_info["status"] = "loaded"

        return status_info

    def start(self, service: str) -> Dict[str, Any]:
        """Pokreni servis."""
        svc = self.SERVICES.get(service)
        if not svc:
            return {"error": f"Unknown service: {service}"}

        result = self.executor.exec(
            f"launchctl load ~/Library/LaunchAgents/{svc['plist']}.plist 2>&1 || "
            f"launchctl start {svc['plist']}"
        )
        time.sleep(2)
        return {"action": "start", "service": service,
                "result": result, "status": self._check_service(service)}

    def stop(self, service: str) -> Dict[str, Any]:
        """Zaustavi servis."""
        svc = self.SERVICES.get(service)
        if not svc:
            return {"error": f"Unknown service: {service}"}

        result = self.executor.exec(f"launchctl stop {svc['plist']}")
        return {"action": "stop", "service": service, "result": result}

    def restart(self, service: str) -> Dict[str, Any]:
        """Restartaj servis."""
        self.stop(service)
        time.sleep(2)
        return self.start(service)

    def restart_all(self) -> Dict[str, Any]:
        """Restartaj sve servise."""
        results = {}
        for svc_name in ["nyx-mlx", "nyx-api"]:  # MLX first (dependency)
            results[svc_name] = self.restart(svc_name)
            time.sleep(3)
        return results

    def logs(self, service: str, lines: int = 50,
             follow: bool = False) -> Dict[str, Any]:
        """Dohvati logove servisa."""
        log_file = f"{self.executor.conn.log_dir}/{service}.log"

        if follow:
            # Za follow koristimo timeout
            cmd = f"tail -f {log_file}"
            return {"command": f"{self.executor.conn.ssh_cmd} '{cmd}'",
                    "note": "Run this command in bash_tool for live logs"}

        result = self.executor.exec(f"tail -n {lines} {log_file}")
        return {
            "service": service,
            "lines": lines,
            "log": result.get("stdout", ""),
            "success": result.get("success", False),
        }

    def health_check(self) -> Dict[str, Any]:
        """Kompletna zdravstvena provjera sustava."""
        health = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "system": {},
        }

        # Servisi
        for svc_name in self.SERVICES:
            health["services"][svc_name] = self._check_service(svc_name)

        # Sistem
        sys_info = self.executor.exec(
            "echo \"$(sysctl -n hw.memsize);"
            "$(vm_stat | grep 'Pages free' | awk '{print $3}' | tr -d '.');"
            "$(df -h / | tail -1 | awk '{print $4}');"
            "$(uptime | awk -F'load averages:' '{print $2}');"
            "$(top -l 1 | grep 'CPU usage' | head -1)\""
        )
        if sys_info.get("success"):
            parts = sys_info["stdout"].split(";")
            total_mem = int(parts[0]) // (1024**3) if len(parts) > 0 else 0
            health["system"] = {
                "total_ram_gb": total_mem,
                "disk_free": parts[2].strip() if len(parts) > 2 else "unknown",
                "load_avg": parts[3].strip() if len(parts) > 3 else "unknown",
                "cpu_usage": parts[4].strip() if len(parts) > 4 else "unknown",
            }

        # GPU / Neural Engine
        gpu_info = self.executor.exec(
            "system_profiler SPDisplaysDataType 2>/dev/null | grep 'Chip\\|Cores\\|Metal' | head -5"
        )
        if gpu_info.get("success"):
            health["system"]["gpu_info"] = gpu_info["stdout"].strip()

        return health


# ═══════════════════════════════════════════
# DEPLOYER — Git Pull + Restart
# ═══════════════════════════════════════════

class Deployer:
    """
    Deploy ciklus: git pull → test → restart.

    Dva načina:
      1. GitHub Deploy: push → pull → restart
      2. Direct Deploy: SCP datoteku → restart modula
    """

    def __init__(self, executor: RemoteExecutor = None,
                 services: ServiceManager = None):
        self.executor = executor or RemoteExecutor()
        self.services = services or ServiceManager(self.executor)

    def deploy_from_github(self, run_tests: bool = True) -> Dict[str, Any]:
        """
        Puni deploy ciklus:
        1. git pull origin main
        2. pip install (ako treba)
        3. pytest (opcijski)
        4. restart servisa
        """
        deploy_log = {
            "started_at": datetime.now().isoformat(),
            "steps": [],
        }

        # Step 1: Git pull
        pull = self.executor.exec_in_project("git pull origin main")
        deploy_log["steps"].append({
            "step": "git_pull",
            "success": pull.get("success"),
            "output": pull.get("stdout", "")[:500],
        })
        if not pull.get("success"):
            deploy_log["status"] = "failed"
            deploy_log["error"] = "Git pull failed"
            return deploy_log

        # Step 2: Check for new dependencies
        if "requirements" in pull.get("stdout", "") or "pyproject" in pull.get("stdout", ""):
            pip_install = self.executor.exec_in_venv(
                "pip install -e . 2>&1 | tail -5"
            )
            deploy_log["steps"].append({
                "step": "pip_install",
                "success": pip_install.get("success"),
                "output": pip_install.get("stdout", "")[:300],
            })

        # Step 3: Run tests (optional)
        if run_tests:
            tests = self.executor.exec_in_venv(
                "python -m pytest tests/ -q --tb=line 2>&1 | tail -10",
                timeout=120
            )
            deploy_log["steps"].append({
                "step": "tests",
                "success": tests.get("success"),
                "output": tests.get("stdout", "")[:500],
            })
            if not tests.get("success"):
                deploy_log["status"] = "failed"
                deploy_log["error"] = "Tests failed — deployment aborted"
                return deploy_log

        # Step 4: Restart services
        restart = self.services.restart_all()
        deploy_log["steps"].append({
            "step": "restart",
            "success": all(
                r.get("status", {}).get("status") == "running"
                for r in restart.values()
                if isinstance(r, dict) and "status" in r
            ),
            "services": restart,
        })

        # Step 5: Health check
        time.sleep(3)
        health = self.services.health_check()
        deploy_log["steps"].append({
            "step": "health_check",
            "health": health,
        })

        deploy_log["status"] = "success"
        deploy_log["finished_at"] = datetime.now().isoformat()
        return deploy_log

    def deploy_file(self, local_path: str, remote_relative_path: str,
                    restart_service: str = "nyx-api") -> Dict[str, Any]:
        """
        Brzi deploy jedne datoteke:
        1. SCP na Mac Studio
        2. Restart specifičnog servisa
        """
        remote_full = f"{self.executor.conn.project_path}/{remote_relative_path}"

        # Backup originala
        self.executor.exec(f"cp {remote_full} {remote_full}.bak 2>/dev/null || true")

        # Upload
        upload = self.executor.upload_file(local_path, remote_full)
        if not upload.get("success"):
            return {"success": False, "error": "Upload failed", "details": upload}

        # Restart
        if restart_service:
            restart = self.services.restart(restart_service)
            return {
                "success": True,
                "file": remote_relative_path,
                "restart": restart,
            }

        return {"success": True, "file": remote_relative_path}

    def rollback_file(self, remote_relative_path: str,
                      restart_service: str = "nyx-api") -> Dict[str, Any]:
        """Vrati backup verziju datoteke."""
        remote_full = f"{self.executor.conn.project_path}/{remote_relative_path}"
        result = self.executor.exec(f"cp {remote_full}.bak {remote_full}")

        if restart_service:
            self.services.restart(restart_service)

        return {"success": result.get("success"), "rolled_back": remote_relative_path}

    def get_diff(self) -> Dict[str, Any]:
        """Prikaži razlike između lokalnog i remote koda."""
        return self.executor.exec_in_project("git diff --stat HEAD")

    def get_log(self, n: int = 10) -> Dict[str, Any]:
        """Zadnjih N commitova."""
        return self.executor.exec_in_project(
            f"git log --oneline -n {n}"
        )


# ═══════════════════════════════════════════
# LIVE DEBUGGER
# ═══════════════════════════════════════════

class LiveDebugger:
    """
    Alati za live debugging na Mac Studiju.

    Omogućuje:
      - Pregled logova u realnom vremenu
      - Python REPL na remote sustavu
      - Provjeru stanja memorije, modela, sesija
      - Pokretanje specifičnih testova
    """

    def __init__(self, executor: RemoteExecutor = None):
        self.executor = executor or RemoteExecutor()
        self.conn = self.executor.conn

    def tail_logs(self, service: str = "nyx-api",
                  lines: int = 100, grep: str = "") -> Dict[str, Any]:
        """Dohvati zadnje logove, opcionalno filtrirane."""
        log_file = f"{self.conn.log_dir}/{service}.log"
        cmd = f"tail -n {lines} {log_file}"
        if grep:
            cmd += f" | grep -i {shlex.quote(grep)}"
        return self.executor.exec(cmd, timeout=15)

    def search_logs(self, pattern: str, service: str = "nyx-api",
                    context: int = 3) -> Dict[str, Any]:
        """Pretraži logove po patternu."""
        log_file = f"{self.conn.log_dir}/{service}.log"
        return self.executor.exec(
            f"grep -n -C {context} -i {shlex.quote(pattern)} {log_file} | tail -50",
            timeout=15
        )

    def errors_today(self, service: str = "nyx-api") -> Dict[str, Any]:
        """Prikaži sve greške od danas."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = f"{self.conn.log_dir}/{service}.log"
        return self.executor.exec(
            f"grep -i 'error\\|exception\\|traceback' {log_file} | "
            f"grep '{today}' | tail -30",
            timeout=15
        )

    def run_python(self, code: str) -> Dict[str, Any]:
        """Izvrši Python kod na Mac Studiju u project kontekstu."""
        escaped = code.replace("'", "'\\''")
        return self.executor.exec_in_venv(
            f"python3 -c '{escaped}'",
            timeout=30
        )

    def check_memory_tiers(self) -> Dict[str, Any]:
        """Provjeri stanje 4-Tier Memory sustava."""
        return self.run_python("""
import json, sqlite3, os
data_dir = '/opt/nyx-light-racunovodja/data'

# L2 Semantic
l2_path = os.path.join(data_dir, 'semantic_rules.db')
l2_count = 0
if os.path.exists(l2_path):
    conn = sqlite3.connect(l2_path)
    l2_count = conn.execute('SELECT COUNT(*) FROM rules').fetchone()[0]
    conn.close()

# L3 DPO
dpo_path = os.path.join(data_dir, 'dpo_corrections.db')
dpo_count = 0
if os.path.exists(dpo_path):
    conn = sqlite3.connect(dpo_path)
    dpo_count = conn.execute('SELECT COUNT(*) FROM corrections').fetchone()[0]
    conn.close()

print(json.dumps({'L2_rules': l2_count, 'L3_corrections': dpo_count}))
""")

    def check_rag_stats(self) -> Dict[str, Any]:
        """Provjeri stanje RAG baze zakona."""
        return self.run_python("""
import json, sqlite3
conn = sqlite3.connect('/opt/nyx-light-racunovodja/data/laws.db')
total = conn.execute('SELECT COUNT(*) FROM law_chunks').fetchone()[0]
current = conn.execute("SELECT COUNT(*) FROM law_chunks WHERE valid_to = '' OR valid_to IS NULL").fetchone()[0]
conn.close()
print(json.dumps({'total_chunks': total, 'current': current, 'expired': total - current}))
""")

    def check_active_sessions(self) -> Dict[str, Any]:
        """Provjeri aktivne korisničke sesije."""
        return self.executor.exec(
            f"curl -s http://localhost:{self.conn.api_port}/api/v1/system/sessions 2>/dev/null || echo 'API not responding'",
            timeout=10
        )

    def check_model_loaded(self) -> Dict[str, Any]:
        """Provjeri je li LLM model učitan u memoriju."""
        return self.executor.exec(
            f"curl -s http://localhost:{self.conn.mlx_port}/health 2>/dev/null || echo 'MLX not responding'",
            timeout=10
        )

    def run_single_test(self, test_path: str) -> Dict[str, Any]:
        """Pokreni specifičan test na remote sustavu."""
        return self.executor.exec_in_venv(
            f"python -m pytest {test_path} -v --tb=short 2>&1 | tail -30",
            timeout=60
        )

    def run_all_tests(self) -> Dict[str, Any]:
        """Pokreni sve testove na remote sustavu."""
        return self.executor.exec_in_venv(
            "python -m pytest tests/ -q --tb=line 2>&1 | tail -20",
            timeout=180
        )

    def check_disk_space(self) -> Dict[str, Any]:
        """Provjeri disk prostor."""
        return self.executor.exec("df -h / /opt 2>/dev/null | tail -5")

    def check_gpu_memory(self) -> Dict[str, Any]:
        """Provjeri zauzeće Unified Memory (M-series)."""
        return self.executor.exec(
            "sudo memory_pressure 2>/dev/null || "
            "vm_stat | head -10"
        )

    def process_list(self) -> Dict[str, Any]:
        """Top procesi po memoriji."""
        return self.executor.exec(
            "ps aux --sort=-%mem | head -15"
        )


# ═══════════════════════════════════════════
# SETUP GENERATOR — Skripta za Mac Studio
# ═══════════════════════════════════════════

class MacStudioSetup:
    """Generira setup skripte za inicijalno postavljanje Mac Studija."""

    @staticmethod
    def generate_initial_setup() -> str:
        """Kompletna skripta za prvi setup Mac Studija."""
        return '''#!/bin/bash
# ═══════════════════════════════════════════
# NYX LIGHT — INICIJALNI SETUP MAC STUDIJA
# ═══════════════════════════════════════════
# Pokreni: bash setup_mac_studio.sh
set -e

echo "╔══════════════════════════════════════╗"
echo "║  Nyx Light — Mac Studio Setup v3.0   ║"
echo "╚══════════════════════════════════════╝"

# 1. Kreiraj korisnika
echo "\\n[1/8] Kreiram nyx korisnika..."
sudo dscl . -create /Users/nyx
sudo dscl . -create /Users/nyx UserShell /bin/zsh
sudo dscl . -create /Users/nyx UniqueID 550
sudo dscl . -create /Users/nyx PrimaryGroupID 20
sudo dscl . -create /Users/nyx NFSHomeDirectory /Users/nyx
sudo mkdir -p /Users/nyx
sudo chown nyx:staff /Users/nyx

# 2. Omogući SSH
echo "[2/8] Omogućujem SSH (Remote Login)..."
sudo systemsetup -setremotelogin on
sudo launchctl load -w /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || true

# 3. SSH ključ za Claude
echo "[3/8] Postavljam SSH autorizaciju..."
mkdir -p /Users/nyx/.ssh
chmod 700 /Users/nyx/.ssh
touch /Users/nyx/.ssh/authorized_keys
chmod 600 /Users/nyx/.ssh/authorized_keys
echo "# Dodajte Claude SSH public key ovdje:" >> /Users/nyx/.ssh/authorized_keys
echo "# ssh-ed25519 AAAA... claude@anthropic" >> /Users/nyx/.ssh/authorized_keys
chown -R nyx:staff /Users/nyx/.ssh

# 4. Instaliraj Homebrew
echo "[4/8] Instaliram Homebrew..."
if ! command -v brew &>/dev/null; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# 5. Instaliraj Python, Node, Git
echo "[5/8] Instaliram alate..."
brew install python@3.12 node git tailscale

# 6. Kloniraj repo
echo "[6/8] Kloniram Nyx Light repo..."
sudo mkdir -p /opt/nyx-light-racunovodja
sudo chown nyx:staff /opt/nyx-light-racunovodja
cd /opt/nyx-light-racunovodja
git clone https://github.com/mladen1312/nyx-light-racunovodja.git .

# 7. Python venv
echo "[7/8] Kreiram Python okruženje..."
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install vllm-mlx pytest

# 8. Direktoriji
echo "[8/8] Kreiram direktorije..."
mkdir -p logs data data/models data/backups

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✅ Setup završen!                    ║"
echo "║                                      ║"
echo "║  Sljedeći koraci:                    ║"
echo "║  1. Dodajte SSH ključ u              ║"
echo "║     /Users/nyx/.ssh/authorized_keys  ║"
echo "║  2. Instalirajte launchd servise     ║"
echo "║  3. Preuzmite AI modele              ║"
echo "╚══════════════════════════════════════╝"
'''

    @staticmethod
    def generate_launchd_api_plist() -> str:
        """launchd plist za API server."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/nyx-light-racunovodja/.venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>nyx_light.api.app:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8420</string>
        <string>--workers</string>
        <string>4</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/nyx-light-racunovodja</string>
    <key>StandardOutPath</key>
    <string>/opt/nyx-light-racunovodja/logs/nyx-api.log</string>
    <key>StandardErrorPath</key>
    <string>/opt/nyx-light-racunovodja/logs/nyx-api-error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>NYX_ENV</key>
        <string>production</string>
        <key>NYX_DATA_DIR</key>
        <string>/opt/nyx-light-racunovodja/data</string>
    </dict>
</dict>
</plist>'''

    @staticmethod
    def generate_launchd_mlx_plist() -> str:
        """launchd plist za MLX server."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.mlx</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/nyx-light-racunovodja/.venv/bin/python</string>
        <string>-m</string>
        <string>mlx_lm.server</string>
        <string>--model</string>
        <string>/opt/nyx-light-racunovodja/data/models/Qwen3-235B-A22B-4bit</string>
        <string>--port</string>
        <string>8422</string>
        <string>--host</string>
        <string>127.0.0.1</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/nyx-light-racunovodja</string>
    <key>StandardOutPath</key>
    <string>/opt/nyx-light-racunovodja/logs/nyx-mlx.log</string>
    <key>StandardErrorPath</key>
    <string>/opt/nyx-light-racunovodja/logs/nyx-mlx-error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>'''

    @staticmethod
    def generate_ssh_key_setup_guide() -> str:
        """Uputa za generiranje SSH ključa za Claude pristup."""
        return """
SSH KLJUČ ZA CLAUDE PRISTUP
════════════════════════════

Na VAŠEM računalu (ne Mac Studiju):

1. Generirajte SSH ključ:
   ssh-keygen -t ed25519 -C "claude@nyx-light" -f ~/.ssh/nyx_claude

2. Kopirajte PUBLIC ključ na Mac Studio:
   ssh-copy-id -i ~/.ssh/nyx_claude.pub nyx@nyx-studio

3. U Claude okruženju, koristite:
   MacStudioConnection(
       host="nyx-studio",
       user="nyx",
       key_path="/path/to/nyx_claude"
   )

Alternativno — Tailscale SSH:
   tailscale ssh nyx@nyx-studio
   (Automatska autentikacija, bez ključeva)
"""


# ═══════════════════════════════════════════
# CLI HELPER — Brze komande za Claude bash
# ═══════════════════════════════════════════

class NyxCLI:
    """
    Brze komande za korištenje iz Claude bash_tool-a.
    Svaka metoda vraća gotovu bash komandu.
    """

    def __init__(self, conn: MacStudioConnection = None):
        self.conn = conn or MacStudioConnection()
        self.ssh = self.conn.ssh_cmd

    def cmd_connect_test(self) -> str:
        return f'{self.ssh} "echo OK && hostname && uname -m"'

    def cmd_deploy(self) -> str:
        return (f'{self.ssh} "cd {self.conn.project_path} && '
                f'git pull origin main && '
                f'source .venv/bin/activate && '
                f'python -m pytest tests/ -q --tb=line && '
                f'launchctl stop hr.nyxlight.api && sleep 2 && '
                f'launchctl start hr.nyxlight.api"')

    def cmd_quick_deploy(self) -> str:
        """Deploy bez testova (hitni fix)."""
        return (f'{self.ssh} "cd {self.conn.project_path} && '
                f'git pull origin main && '
                f'launchctl stop hr.nyxlight.api && sleep 2 && '
                f'launchctl start hr.nyxlight.api"')

    def cmd_logs(self, service: str = "nyx-api", lines: int = 50) -> str:
        return f'{self.ssh} "tail -n {lines} {self.conn.log_dir}/{service}.log"'

    def cmd_logs_follow(self, service: str = "nyx-api") -> str:
        return f'{self.ssh} "tail -f {self.conn.log_dir}/{service}.log"'

    def cmd_errors(self, service: str = "nyx-api") -> str:
        return (f'{self.ssh} "grep -i \'error\\|exception\' '
                f'{self.conn.log_dir}/{service}.log | tail -20"')

    def cmd_status(self) -> str:
        return (f'{self.ssh} "echo \\"=== Servisi ===\\" && '
                f'launchctl list | grep nyxlight && '
                f'echo \\"\\n=== Portovi ===\\" && '
                f'lsof -i :8420 -i :8422 2>/dev/null && '
                f'echo \\"\\n=== RAM ===\\" && '
                f'vm_stat | head -5 && '
                f'echo \\"\\n=== Disk ===\\" && '
                f'df -h / | tail -1"')

    def cmd_restart(self, service: str = "nyx-api") -> str:
        plist = ServiceManager.SERVICES.get(service, {}).get("plist", "hr.nyxlight.api")
        return f'{self.ssh} "launchctl stop {plist} && sleep 2 && launchctl start {plist}"'

    def cmd_upload_file(self, local_path: str, remote_rel: str) -> str:
        remote = f"{self.conn.project_path}/{remote_rel}"
        return f'{self.conn.scp_prefix} {local_path} {self.conn.user}@{self.conn.host}:{remote}'

    def cmd_run_tests(self, test_file: str = "") -> str:
        target = test_file or "tests/"
        return (f'{self.ssh} "cd {self.conn.project_path} && '
                f'source .venv/bin/activate && '
                f'python -m pytest {target} -v --tb=short 2>&1 | tail -40"')

    def cmd_python(self, code: str) -> str:
        escaped = code.replace('"', '\\"').replace("'", "'\\''")
        return (f"{self.ssh} \"cd {self.conn.project_path} && "
                f"source .venv/bin/activate && "
                f"python3 -c '{escaped}'\"")

    def cmd_health(self) -> str:
        return (f'{self.ssh} "curl -s http://localhost:8420/api/v1/system/health && '
                f'echo && curl -s http://localhost:8422/health"')

    def print_cheatsheet(self) -> str:
        """Ispiši sve dostupne komande."""
        return f"""
╔════════════════════════════════════════════════════════════════╗
║           NYX LIGHT — REMOTE DEV CHEATSHEET                   ║
╚════════════════════════════════════════════════════════════════╝

═══ KONEKCIJA ═══
  Test:       {self.cmd_connect_test()}

═══ DEPLOY ═══
  Puni:       git push → {self.cmd_deploy()}
  Brzi:       git push → {self.cmd_quick_deploy()}

═══ LOGOVI ═══
  Zadnjih 50: {self.cmd_logs()}
  Live:       {self.cmd_logs_follow()}
  Greške:     {self.cmd_errors()}

═══ SERVISI ═══
  Status:     {self.cmd_status()}
  Restart:    {self.cmd_restart()}
  Health:     {self.cmd_health()}

═══ TESTOVI ═══
  Svi:        {self.cmd_run_tests()}
  Jedan:      {self.cmd_run_tests("tests/test_sprint23.py")}

═══ UPLOAD DATOTEKE ═══
  {self.cmd_upload_file("/home/claude/file.py", "src/nyx_light/file.py")}
"""
