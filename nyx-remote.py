#!/usr/bin/env python3
"""
nyx-remote — CLI za upravljanje Mac Studijem iz Claude okruženja.

Korištenje iz Claude bash_tool-a:
  python nyx-remote.py connect              # Test konekcije
  python nyx-remote.py status               # Status servisa
  python nyx-remote.py deploy               # Git pull + test + restart
  python nyx-remote.py deploy --quick       # Git pull + restart (bez testova)
  python nyx-remote.py logs [service]       # Zadnjih 50 linija logova
  python nyx-remote.py errors [service]     # Greške od danas
  python nyx-remote.py restart [service]    # Restart servisa
  python nyx-remote.py health               # Health check
  python nyx-remote.py tests [path]         # Pokreni testove
  python nyx-remote.py upload <local> <remote>  # Upload datoteke
  python nyx-remote.py python "<code>"      # Izvrši Python kod
  python nyx-remote.py cheatsheet           # Ispiši sve komande

Konfiguracija (env varijable):
  NYX_HOST=nyx-studio          # Mac Studio hostname/IP
  NYX_USER=nyx                  # SSH korisnik
  NYX_PORT=22                   # SSH port
  NYX_KEY=/path/to/key          # SSH ključ (opcionalno)
  NYX_PROJECT=/opt/nyx-light-racunovodja
"""

import json
import os
import sys

# Dodaj project root u path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nyx_light.devops import (
    MacStudioConnection, RemoteExecutor, ServiceManager,
    Deployer, LiveDebugger, NyxCLI
)


def get_connection() -> MacStudioConnection:
    """Kreiraj konekciju iz env varijabli."""
    return MacStudioConnection(
        host=os.environ.get("NYX_HOST", "nyx-studio"),
        user=os.environ.get("NYX_USER", "nyx"),
        port=int(os.environ.get("NYX_PORT", "22")),
        key_path=os.environ.get("NYX_KEY", ""),
        project_path=os.environ.get("NYX_PROJECT", "/opt/nyx-light-racunovodja"),
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    conn = get_connection()
    executor = RemoteExecutor(conn)
    services = ServiceManager(executor)
    deployer = Deployer(executor, services)
    debugger = LiveDebugger(executor)
    cli = NyxCLI(conn)

    if cmd == "connect":
        result = executor.test_connection()
        print(json.dumps(result, indent=2))

    elif cmd == "status":
        result = services.status()
        print(json.dumps(result, indent=2))

    elif cmd == "deploy":
        quick = "--quick" in sys.argv
        if quick:
            print("⚡ Quick deploy (bez testova)...")
            # Git pull + restart
            pull = executor.exec_in_project("git pull origin main")
            print(f"Git pull: {'✅' if pull.get('success') else '❌'}")
            print(pull.get("stdout", ""))
            restart = services.restart_all()
            print(f"Restart: {json.dumps(restart, indent=2)}")
        else:
            print("🚀 Full deploy (pull + test + restart)...")
            result = deployer.deploy_from_github(run_tests=True)
            print(json.dumps(result, indent=2))

    elif cmd == "logs":
        service = sys.argv[2] if len(sys.argv) > 2 else "nyx-api"
        lines = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        result = debugger.tail_logs(service, lines)
        print(result.get("stdout", "No logs"))

    elif cmd == "errors":
        service = sys.argv[2] if len(sys.argv) > 2 else "nyx-api"
        result = debugger.errors_today(service)
        print(result.get("stdout", "No errors today ✅"))

    elif cmd == "restart":
        service = sys.argv[2] if len(sys.argv) > 2 else "nyx-api"
        result = services.restart(service)
        print(json.dumps(result, indent=2))

    elif cmd == "health":
        result = services.health_check()
        print(json.dumps(result, indent=2))

    elif cmd == "tests":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if path:
            result = debugger.run_single_test(path)
        else:
            result = debugger.run_all_tests()
        print(result.get("stdout", ""))

    elif cmd == "upload":
        if len(sys.argv) < 4:
            print("Usage: nyx-remote.py upload <local_path> <remote_relative_path>")
            sys.exit(1)
        result = deployer.deploy_file(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2))

    elif cmd == "python":
        if len(sys.argv) < 3:
            print("Usage: nyx-remote.py python \"<code>\"")
            sys.exit(1)
        result = debugger.run_python(sys.argv[2])
        print(result.get("stdout", ""))
        if result.get("stderr"):
            print(f"STDERR: {result['stderr']}", file=sys.stderr)

    elif cmd == "memory":
        result = debugger.check_memory_tiers()
        print(result.get("stdout", ""))

    elif cmd == "rag":
        result = debugger.check_rag_stats()
        print(result.get("stdout", ""))

    elif cmd == "sessions":
        result = debugger.check_active_sessions()
        print(result.get("stdout", ""))

    elif cmd == "disk":
        result = debugger.check_disk_space()
        print(result.get("stdout", ""))

    elif cmd == "processes":
        result = debugger.process_list()
        print(result.get("stdout", ""))

    elif cmd == "cheatsheet":
        print(cli.print_cheatsheet())

    elif cmd == "rollback":
        if len(sys.argv) < 3:
            print("Usage: nyx-remote.py rollback <remote_relative_path>")
            sys.exit(1)
        result = deployer.rollback_file(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif cmd == "diff":
        result = deployer.get_diff()
        print(result.get("stdout", ""))

    elif cmd == "gitlog":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = deployer.get_log(n)
        print(result.get("stdout", ""))

    else:
        print(f"Nepoznata komanda: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
