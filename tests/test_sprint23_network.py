"""
Tests — Office Network & Employee Access
"""

import pytest


class TestNetworkConfig:
    def test_defaults(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig()
        assert config.hostname == "nyx-studio"
        assert config.api_port == 8420
        assert config.mlx_bind == "127.0.0.1"  # MLX samo lokalno

    def test_lan_url(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig()
        assert config.lan_url == "http://nyx-studio.local:8420"

    def test_tailscale_url(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig()
        assert config.tailscale_url == "http://nyx-studio:8420"

    def test_ssl_url(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig(ssl_enabled=True)
        assert config.lan_url.startswith("https://")

    def test_allowed_private_ips(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig()
        assert config.is_allowed("192.168.1.100") is True
        assert config.is_allowed("10.0.0.5") is True
        assert config.is_allowed("172.16.0.1") is True
        assert config.is_allowed("100.64.1.50") is True  # Tailscale
        assert config.is_allowed("127.0.0.1") is True    # Localhost

    def test_blocked_public_ips(self):
        from nyx_light.modules.network import NetworkConfig
        config = NetworkConfig()
        assert config.is_allowed("8.8.8.8") is False       # Google DNS
        assert config.is_allowed("203.0.113.1") is False    # Public
        assert config.is_allowed("1.1.1.1") is False        # Cloudflare


class TestServiceDiscovery:
    def test_bonjour_plist(self):
        from nyx_light.modules.network import ServiceDiscovery
        plist = ServiceDiscovery.generate_bonjour_plist()
        assert "dns-sd" in plist
        assert "8420" in plist
        assert "Nyx Light" in plist
        assert "hr.nyxlight.bonjour" in plist

    def test_get_local_ips(self):
        from nyx_light.modules.network import ServiceDiscovery
        ips = ServiceDiscovery.get_local_ips()
        assert isinstance(ips, list)
        # May be empty in CI but should not crash

    def test_detect_server_offline(self):
        from nyx_light.modules.network import ServiceDiscovery
        # Will likely return None in test environment
        result = ServiceDiscovery.detect_server(timeout=0.1)
        assert result is None or "url" in result


class TestOnboardingGuide:
    def test_quick_start(self):
        from nyx_light.modules.network import OnboardingGuide, NetworkConfig
        guide = OnboardingGuide.generate_quick_start(
            config=NetworkConfig(),
            username="ana.horvat",
            role="racunovoda",
        )
        assert "nyx-studio.local:8420" in guide
        assert "ana.horvat" in guide
        assert "Računovođa" in guide
        assert "AI PREDLAŽE" in guide
        assert "SVE JE LOKALNO" in guide

    def test_roles(self):
        from nyx_light.modules.network import OnboardingGuide
        roles = OnboardingGuide.ROLES
        assert "admin" in roles
        assert "racunovoda" in roles
        assert "pripravnik" in roles
        assert "readonly" in roles
        assert "approve_entries" in roles["racunovoda"]["permissions"]
        assert "approve_entries" not in roles["pripravnik"]["permissions"]

    def test_tailscale_windows(self):
        from nyx_light.modules.network import OnboardingGuide
        guide = OnboardingGuide.generate_tailscale_setup("windows")
        assert "tailscale.com" in guide
        assert "nyx-studio:8420" in guide

    def test_tailscale_mac(self):
        from nyx_light.modules.network import OnboardingGuide
        guide = OnboardingGuide.generate_tailscale_setup("mac")
        assert "App Store" in guide

    def test_tailscale_iphone(self):
        from nyx_light.modules.network import OnboardingGuide
        guide = OnboardingGuide.generate_tailscale_setup("iphone")
        assert "VPN" in guide


class TestAccessControl:
    def test_allow_lan(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        result = ac.check_access("192.168.1.100", 8420)
        assert result["allowed"] is True
        assert result["method"] == "lan"

    def test_allow_tailscale(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        result = ac.check_access("100.64.1.50", 8420)
        assert result["allowed"] is True
        assert result["method"] == "tailscale"

    def test_allow_localhost(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        result = ac.check_access("127.0.0.1", 8420)
        assert result["allowed"] is True

    def test_block_public_ip(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        result = ac.check_access("8.8.8.8", 8420)
        assert result["allowed"] is False

    def test_mlx_only_localhost(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        # MLX port from LAN = blocked
        result = ac.check_access("192.168.1.100", 8422)
        assert result["allowed"] is False
        assert "MLX" in result["reason"]
        # MLX port from localhost = allowed
        result2 = ac.check_access("127.0.0.1", 8422)
        assert result2["allowed"] is True

    def test_block_ip(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        ac.block_ip("192.168.1.99")
        result = ac.check_access("192.168.1.99", 8420)
        assert result["allowed"] is False
        assert "blocked" in result["reason"]

    def test_stats(self):
        from nyx_light.modules.network import AccessControl
        ac = AccessControl()
        ac.check_access("192.168.1.1")
        ac.check_access("8.8.8.8")
        stats = ac.get_stats()
        assert stats["total_checks"] == 2
        assert stats["allowed"] == 1
        assert stats["denied"] == 1


class TestConnectionDashboard:
    def test_connect_user(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard(max_users=15)
        assert cd.connect("ana", "192.168.1.100", "Chrome/Win") is True
        dash = cd.get_dashboard()
        assert dash["connected"] == 1
        assert dash["available"] == 14

    def test_max_users(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard(max_users=3)
        cd.connect("user1", "192.168.1.1")
        cd.connect("user2", "192.168.1.2")
        cd.connect("user3", "192.168.1.3")
        assert cd.connect("user4", "192.168.1.4") is False  # Full

    def test_reconnect_same_user(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard(max_users=3)
        cd.connect("ana", "192.168.1.1")
        cd.connect("ana", "192.168.1.1")  # Same user reconnect
        assert cd.get_dashboard()["connected"] == 1

    def test_disconnect(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard()
        cd.connect("ana", "192.168.1.1")
        cd.disconnect("ana")
        assert cd.get_dashboard()["connected"] == 0

    def test_by_method(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard()
        cd.connect("ana", "192.168.1.1")       # LAN
        cd.connect("marko", "100.64.1.50")     # Tailscale
        cd.connect("iva", "127.0.0.1")         # Localhost
        dash = cd.get_dashboard()
        assert dash["by_method"]["lan"] == 1
        assert dash["by_method"]["tailscale"] == 1
        assert dash["by_method"]["localhost"] == 1

    def test_ip_masked(self):
        from nyx_light.modules.network import ConnectionDashboard
        cd = ConnectionDashboard()
        cd.connect("ana", "192.168.1.105")
        user = cd.get_dashboard()["users"][0]
        assert "*" in user["ip"]  # IP is masked
        assert "105" in user["ip"]  # Last octet visible


class TestEmployeeAccount:
    def test_create(self):
        from nyx_light.modules.network import EmployeeAccount
        acc = EmployeeAccount(username="ana.horvat", display_name="Ana Horvat")
        assert acc.role == "racunovoda"
        assert "chat" in acc.permissions
        assert "approve_entries" in acc.permissions

    def test_to_dict(self):
        from nyx_light.modules.network import EmployeeAccount
        acc = EmployeeAccount(username="ana", display_name="Ana")
        d = acc.to_dict()
        assert d["username"] == "ana"
        assert d["active"] is True


class TestNetworkSetupGenerator:
    def test_firewall_script(self):
        from nyx_light.modules.network import NetworkSetupGenerator
        script = NetworkSetupGenerator.generate_firewall_script()
        assert "192.168.0.0/16" in script
        assert "100.64.0.0/10" in script
        assert "8422" in script

    def test_static_ip_guide(self):
        from nyx_light.modules.network import NetworkSetupGenerator
        guide = NetworkSetupGenerator.generate_static_ip_guide()
        assert "192.168" in guide
        assert "nyx-studio.local" in guide

    def test_router_dns_guide(self):
        from nyx_light.modules.network import NetworkSetupGenerator
        guide = NetworkSetupGenerator.generate_router_dns_guide()
        assert "nyx-studio" in guide

    def test_windows_hosts(self):
        from nyx_light.modules.network import NetworkSetupGenerator
        guide = NetworkSetupGenerator.generate_windows_hosts_entry()
        assert "hosts" in guide
        assert "nyx-studio" in guide
        assert "Tailscale" in guide
