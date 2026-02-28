"""
Tests — DevOps Remote Management Toolkit
"""
import json
import os
import pytest


class TestMacStudioConnection:
    def test_defaults(self):
        from nyx_light.devops import MacStudioConnection
        conn = MacStudioConnection()
        assert conn.host == "nyx-studio"
        assert conn.user == "nyx"
        assert conn.port == 22
        assert conn.api_port == 8420
        assert conn.mlx_port == 8422

    def test_ssh_cmd(self):
        from nyx_light.devops import MacStudioConnection
        conn = MacStudioConnection(host="192.168.1.50", user="admin")
        assert "admin@192.168.1.50" in conn.ssh_cmd
        assert "StrictHostKeyChecking=no" in conn.ssh_cmd

    def test_ssh_with_key(self):
        from nyx_light.devops import MacStudioConnection
        conn = MacStudioConnection(key_path="/home/claude/.ssh/nyx_key")
        assert "-i /home/claude/.ssh/nyx_key" in conn.ssh_cmd

    def test_scp_prefix(self):
        from nyx_light.devops import MacStudioConnection
        conn = MacStudioConnection()
        assert "scp" in conn.scp_prefix
        assert "-P 22" in conn.scp_prefix

    def test_to_dict(self):
        from nyx_light.devops import MacStudioConnection
        d = MacStudioConnection().to_dict()
        assert d["host"] == "nyx-studio"
        assert d["api_port"] == 8420


class TestRemoteExecutor:
    def test_exec_local_fallback(self):
        """Test s localhost (ne treba SSH)."""
        from nyx_light.devops import RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost", user=os.environ.get("USER", "claude"))
        executor = RemoteExecutor(conn)
        # Ova komanda neće raditi bez SSH, ali testira strukturu
        result = executor.exec("echo test", timeout=5)
        # Returncode -1 or 255 if SSH fails, that's OK for unit test
        assert "command" in result
        assert "returncode" in result

    def test_history_tracking(self):
        from nyx_light.devops import RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost")
        executor = RemoteExecutor(conn)
        executor.exec("echo 1", timeout=3)
        executor.exec("echo 2", timeout=3)
        history = executor.get_history()
        assert len(history) == 2
        assert history[0]["command"] == "echo 1"

    def test_exec_timeout(self):
        from nyx_light.devops import RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="192.0.2.1")  # Non-routable IP
        executor = RemoteExecutor(conn)
        result = executor.exec("echo test", timeout=2)
        # Should timeout or fail, not crash
        assert result["success"] is False


class TestServiceManager:
    def test_services_defined(self):
        from nyx_light.devops import ServiceManager
        assert "nyx-api" in ServiceManager.SERVICES
        assert "nyx-mlx" in ServiceManager.SERVICES
        assert "nyx-dpo" in ServiceManager.SERVICES
        assert ServiceManager.SERVICES["nyx-api"]["port"] == 8420
        assert ServiceManager.SERVICES["nyx-mlx"]["port"] == 8422

    def test_unknown_service(self):
        from nyx_light.devops import ServiceManager, RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost")
        sm = ServiceManager(RemoteExecutor(conn))
        result = sm.status("nonexistent")
        assert "error" in result


class TestDeployer:
    def test_get_diff_structure(self):
        from nyx_light.devops import Deployer, RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost")
        deployer = Deployer(RemoteExecutor(conn))
        result = deployer.get_diff()
        assert "command" in result

    def test_get_log_structure(self):
        from nyx_light.devops import Deployer, RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost")
        deployer = Deployer(RemoteExecutor(conn))
        result = deployer.get_log(5)
        assert "command" in result


class TestLiveDebugger:
    def test_run_python_structure(self):
        from nyx_light.devops import LiveDebugger, RemoteExecutor, MacStudioConnection
        conn = MacStudioConnection(host="localhost")
        debugger = LiveDebugger(RemoteExecutor(conn))
        result = debugger.run_python("print('hello')")
        assert "command" in result


class TestNyxCLI:
    def test_cheatsheet(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        sheet = cli.print_cheatsheet()
        assert "DEPLOY" in sheet
        assert "LOGOVI" in sheet
        assert "SERVISI" in sheet
        assert "nyx-studio" in sheet

    def test_deploy_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        cmd = cli.cmd_deploy()
        assert "git pull" in cmd
        assert "pytest" in cmd
        assert "launchctl" in cmd

    def test_quick_deploy_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        cmd = cli.cmd_quick_deploy()
        assert "git pull" in cmd
        assert "pytest" not in cmd

    def test_logs_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "tail" in cli.cmd_logs()
        assert "nyx-api.log" in cli.cmd_logs()

    def test_errors_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "error" in cli.cmd_errors().lower()

    def test_status_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "nyxlight" in cli.cmd_status()
        assert "8420" in cli.cmd_status()

    def test_restart_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "launchctl" in cli.cmd_restart("nyx-api")

    def test_health_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "curl" in cli.cmd_health()
        assert "8420" in cli.cmd_health()

    def test_upload_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        cmd = cli.cmd_upload_file("/tmp/test.py", "src/nyx_light/test.py")
        assert "scp" in cmd
        assert "test.py" in cmd

    def test_run_tests_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "pytest" in cli.cmd_run_tests()
        assert "tests/" in cli.cmd_run_tests()

    def test_connect_cmd(self):
        from nyx_light.devops import NyxCLI
        cli = NyxCLI()
        assert "hostname" in cli.cmd_connect_test()

    def test_custom_connection(self):
        from nyx_light.devops import NyxCLI, MacStudioConnection
        conn = MacStudioConnection(host="10.0.0.5", user="mladen", port=2222)
        cli = NyxCLI(conn)
        assert "mladen@10.0.0.5" in cli.cmd_connect_test()
        assert "-p 2222" in cli.cmd_connect_test()


class TestMacStudioSetup:
    def test_initial_setup_script(self):
        from nyx_light.devops import MacStudioSetup
        script = MacStudioSetup.generate_initial_setup()
        assert "#!/bin/bash" in script
        assert "nyx" in script
        assert "ssh" in script.lower()
        assert "brew" in script
        assert "python3.12" in script
        assert "git clone" in script

    def test_api_plist(self):
        from nyx_light.devops import MacStudioSetup
        plist = MacStudioSetup.generate_launchd_api_plist()
        assert "hr.nyxlight.api" in plist
        assert "8420" in plist
        assert "uvicorn" in plist

    def test_mlx_plist(self):
        from nyx_light.devops import MacStudioSetup
        plist = MacStudioSetup.generate_launchd_mlx_plist()
        assert "hr.nyxlight.mlx" in plist
        assert "8422" in plist
        assert "127.0.0.1" in plist  # MLX samo localhost

    def test_ssh_guide(self):
        from nyx_light.devops import MacStudioSetup
        guide = MacStudioSetup.generate_ssh_key_setup_guide()
        assert "ssh-keygen" in guide
        assert "ed25519" in guide
        assert "ssh-copy-id" in guide
