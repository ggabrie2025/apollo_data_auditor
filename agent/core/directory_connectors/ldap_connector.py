"""
LDAP / Active Directory Connector
==================================

Connecteur pour annuaires LDAP on-prem et Active Directory.
Utilise ldap3 (pure Python, cross-platform Linux/Windows/macOS).

CONTRAT INDUSTRIEL: scores=None. L'agent envoie des compteurs agreges,
ZERO donnee nominative. Le scoring est fait cote Cloud.

Sprint 87 — G6 Connecteur Active Directory / LDAP
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from typing import Dict, Any, List, Optional
import logging
import importlib

from .base import (
    DirectoryConnector,
    DirectoryCapabilities,
    DirectoryDependencyError,
)
from .registry import register_directory_connector

logger = logging.getLogger(__name__)

# Admin group CNs to detect (AD standard + OpenLDAP convention)
_ADMIN_GROUP_PATTERNS = [
    "Domain Admins", "Domain_Admins",
    "Enterprise Admins", "Enterprise_Admins",
    "Schema Admins", "Schema_Admins",
    "Administrateurs du domaine",
    "Administrators",
]


@register_directory_connector
class LDAPConnector(DirectoryConnector):
    """
    Connecteur LDAP / Active Directory on-prem.

    Supporte:
    - OpenLDAP (inetOrgPerson, groupOfNames)
    - Active Directory (user, group, userAccountControl)
    - SSL/TLS (port 636 ou STARTTLS)

    Detection auto AD vs OpenLDAP via rootDSE.
    """

    METADATA = {
        "dir_type": "ldap",
        "name": "LDAP / Active Directory",
        "default_port": 389,
        "ports_to_scan": [389, 636, 3268, 3269],
        "requires": ["ldap3"],
    }

    CAPABILITIES = (
        DirectoryCapabilities.CAN_LIST_USERS
        | DirectoryCapabilities.CAN_LIST_GROUPS
        | DirectoryCapabilities.CAN_READ_POLICY
        | DirectoryCapabilities.CAN_READ_ADMINS
        | DirectoryCapabilities.CAN_READ_SERVICE_ACCOUNTS
    )

    def __init__(self, config: Dict[str, Any]):
        """
        Config attendue:
            host, port, bind_dn, bind_password, base_dn,
            use_ssl (bool), timeout (int, default 30)
        """
        super().__init__(config)
        self._is_ad: Optional[bool] = None
        self._ldap3 = None

    def _validate_dependencies(self) -> None:
        """Verifie que ldap3 est installe."""
        try:
            self._ldap3 = importlib.import_module("ldap3")
        except ImportError:
            raise DirectoryDependencyError(
                "ldap3 is required for LDAP/AD connector",
                missing=["ldap3"],
                instructions="pip install ldap3",
            )

    def _ensure_ldap3(self):
        """Lazy import ldap3 si pas encore charge."""
        if self._ldap3 is None:
            self._ldap3 = importlib.import_module("ldap3")
        return self._ldap3

    async def _connect(self):
        """Etablit connexion LDAP si pas deja connecte.

        Fallback strategy: NTLM (AD Windows) -> SIMPLE (OpenLDAP, AD permissif).
        AD Windows refuse SIMPLE bind par defaut depuis Server 2019 (KB4520011).
        """
        if self.connection is not None:
            return

        ldap3 = self._ensure_ldap3()

        host = self.config.get("host", "localhost")
        port = self.config.get("port", 389)
        use_ssl = self.config.get("use_ssl", False)
        bind_dn = self.config.get("bind_dn", "")
        bind_password = self.config.get("bind_password", "")

        server = ldap3.Server(
            host, port=port, use_ssl=use_ssl,
            get_info=ldap3.ALL,
            connect_timeout=self.timeout,
        )

        # Try NTLM first (AD Windows), then SIMPLE (OpenLDAP)
        last_error = None
        for auth_method in (ldap3.NTLM, ldap3.SIMPLE):
            try:
                user = bind_dn
                # NTLM requires DOMAIN\\user format — convert UPN if needed
                if auth_method == ldap3.NTLM and "@" in bind_dn:
                    domain, _, _ = bind_dn.partition("@")
                    fqdn = bind_dn.split("@")[1]
                    netbios = fqdn.split(".")[0].upper()
                    user = f"{netbios}\\{domain}"

                conn = ldap3.Connection(
                    server, user, bind_password,
                    authentication=auth_method,
                    auto_bind=True,
                    read_only=True,
                    receive_timeout=self.timeout,
                )
                logger.info(f"LDAP bind OK with {auth_method}")
                self.connection = conn
                self._detect_directory_type()
                return
            except Exception as e:
                last_error = e
                logger.debug(f"LDAP bind {auth_method} failed: {e}")
                continue

        raise last_error

    def _detect_directory_type(self):
        """Detecte si c'est un Active Directory ou OpenLDAP via rootDSE."""
        if self.connection is None:
            return
        try:
            info = self.connection.server.info
            if info and info.other:
                # AD expose 'forestFunctionality' dans rootDSE
                if "forestFunctionality" in info.other:
                    self._is_ad = True
                    logger.info("Detected Active Directory")
                    return
            self._is_ad = False
            logger.info("Detected OpenLDAP / generic LDAP")
        except Exception:
            self._is_ad = False

    @property
    def base_dn(self) -> str:
        return self.config.get("base_dn", "")

    def _search(self, search_filter: str, attributes: List[str],
                search_base: str = None, size_limit: int = 0) -> list:
        """Wrapper synchrone pour recherche LDAP. Retourne entries."""
        if self.connection is None:
            return []
        base = search_base or self.base_dn
        self.connection.search(
            base, search_filter,
            attributes=attributes,
            size_limit=size_limit,
        )
        return self.connection.entries[:]

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================

    async def test_connection(self) -> Dict[str, Any]:
        """Test connexion et retourne compteur users."""
        try:
            await self._connect()
            entries = self._search(
                "(objectClass=inetOrgPerson)" if not self._is_ad else "(objectClass=user)",
                ["uid" if not self._is_ad else "sAMAccountName"],
                size_limit=1,
            )
            return {
                "success": True,
                "users_count": len(entries),
                "message": f"Connected to {'AD' if self._is_ad else 'LDAP'}. {len(entries)} users found.",
                "directory_type": "ad" if self._is_ad else "ldap",
            }
        except Exception as e:
            return {
                "success": False,
                "users_count": 0,
                "message": "Connection failed",
                "error": str(e),
            }

    async def get_users_summary(self) -> Dict[str, Any]:
        """
        Compteurs agreges utilisateurs (ZERO donnee nominative).

        Returns: {total, active, dormant_90d, service_accounts,
                  pwd_no_expire, disabled_in_groups}
        """
        await self._connect()

        if self._is_ad:
            return await self._get_users_summary_ad()
        return await self._get_users_summary_ldap()

    async def _get_users_summary_ad(self) -> Dict[str, Any]:
        """Users summary pour Active Directory (userAccountControl flags)."""
        # All users (exclude computer accounts)
        all_users = self._search(
            "(&(objectClass=user)(!(objectClass=computer)))",
            ["userAccountControl", "lastLogonTimestamp",
             "servicePrincipalName", "memberOf"],
        )
        total = len(all_users)
        disabled = 0
        dormant = 0
        service_accounts = 0
        pwd_no_expire = 0
        disabled_in_groups = 0

        # UAC flags
        UAC_DISABLED = 0x0002
        UAC_PWD_NO_EXPIRE = 0x10000

        for user in all_users:
            uac = int(user.userAccountControl.value) if hasattr(user, "userAccountControl") and user.userAccountControl.value else 0
            is_disabled = bool(uac & UAC_DISABLED)

            # Password never expires
            if uac & UAC_PWD_NO_EXPIRE:
                pwd_no_expire += 1

            # Service accounts (have SPN)
            if hasattr(user, "servicePrincipalName") and user.servicePrincipalName.value:
                service_accounts += 1

            # Disabled but still in groups
            if is_disabled:
                disabled += 1
                member_of = user.memberOf.values if hasattr(user, "memberOf") and user.memberOf.values else []
                if member_of:
                    disabled_in_groups += 1

            # Dormant: lastLogonTimestamp > 90 days (AD uses Windows FileTime)
            if not is_disabled and hasattr(user, "lastLogonTimestamp") and user.lastLogonTimestamp.value:
                import datetime
                last_logon = user.lastLogonTimestamp.value
                if isinstance(last_logon, datetime.datetime):
                    days_since = (datetime.datetime.now(datetime.timezone.utc) - last_logon).days
                    if days_since > 90:
                        dormant += 1

        active = total - disabled - dormant

        return {
            "total": total,
            "active": max(0, active),
            "dormant_90d": dormant,
            "service_accounts": service_accounts,
            "pwd_no_expire": pwd_no_expire,
            "disabled_in_groups": disabled_in_groups,
        }

    async def _get_users_summary_ldap(self) -> Dict[str, Any]:
        """
        Users summary pour OpenLDAP (inetOrgPerson).

        OpenLDAP n'a pas userAccountControl. On utilise les conventions:
        - description contient 'DISABLED' pour comptes desactives
        - description contient 'DORMANT' pour comptes dormants
        - OU=ServiceAccounts pour comptes de service
        - description contient 'PWD_NO_EXPIRE' ou attribut pwdPolicySubentry
        """
        all_users = self._search(
            "(objectClass=inetOrgPerson)",
            ["uid", "description"],
        )
        total = len(all_users)

        # Service accounts (in ServiceAccounts OU)
        svc_users = self._search(
            "(objectClass=inetOrgPerson)",
            ["uid"],
            search_base=f"ou=ServiceAccounts,{self.base_dn}",
        )
        service_accounts = len(svc_users)

        # Parse descriptions for flags
        disabled = 0
        dormant = 0
        pwd_no_expire = 0
        disabled_in_groups = 0

        # Get all groups and their members for disabled_in_groups check
        groups = self._search(
            "(objectClass=groupOfNames)",
            ["member"],
        )
        all_group_members = set()
        for g in groups:
            if hasattr(g, "member") and g.member.values:
                for m in g.member.values:
                    all_group_members.add(m.lower())

        for user in all_users:
            desc = str(user.description) if hasattr(user, "description") and user.description.value else ""
            user_dn = user.entry_dn.lower()

            is_disabled = "DISABLED" in desc.upper()
            is_dormant = "DORMANT" in desc.upper()

            if is_disabled:
                disabled += 1
                if user_dn in all_group_members:
                    disabled_in_groups += 1

            if is_dormant:
                dormant += 1

            # pwd_no_expire: service accounts + explicit flag in description
            if "SERVICE ACCOUNT" in desc.upper() or "PWD_NO_EXPIRE" in desc.upper():
                pwd_no_expire += 1

        active = total - disabled - dormant

        return {
            "total": total,
            "active": max(0, active),
            "dormant_90d": dormant,
            "service_accounts": service_accounts,
            "pwd_no_expire": pwd_no_expire,
            "disabled_in_groups": disabled_in_groups,
        }

    async def get_groups_summary(self) -> Dict[str, Any]:
        """Compteurs agreges groupes."""
        await self._connect()

        if self._is_ad:
            group_filter = "(objectClass=group)"
            member_attr = "member"
        else:
            group_filter = "(objectClass=groupOfNames)"
            member_attr = "member"

        groups = self._search(group_filter, [member_attr, "cn"])

        total = len(groups)
        empty = 0
        large_50plus = 0

        for g in groups:
            members = g[member_attr].values if hasattr(g, member_attr) and g[member_attr].values else []
            # groupOfNames requires at least 1 member (often admin placeholder)
            # Count placeholder-only groups as empty
            real_members = [m for m in members if not m.startswith("cn=admin,")]
            if len(real_members) == 0:
                empty += 1
            if len(real_members) >= 50:
                large_50plus += 1

        return {
            "total": total,
            "empty_groups": empty,
            "large_groups_50plus": large_50plus,
        }

    async def get_password_policy(self) -> Dict[str, Any]:
        """
        Politique mot de passe du domaine.

        AD: Lecture attributs du domaine (minPwdLength, pwdHistoryLength, lockoutThreshold, maxPwdAge).
        OpenLDAP: Lecture overlay ppolicy si configure, sinon defaults.
        """
        await self._connect()

        if self._is_ad:
            return await self._get_password_policy_ad()
        return await self._get_password_policy_ldap()

    async def _get_password_policy_ad(self) -> Dict[str, Any]:
        """Password policy AD: attributs du domain root."""
        entries = self._search(
            "(objectClass=domain)",
            ["minPwdLength", "pwdHistoryLength", "lockoutThreshold", "maxPwdAge"],
            search_base=self.base_dn,
            size_limit=1,
        )
        if not entries:
            return self._default_password_policy()

        domain = entries[0]

        min_length = int(domain.minPwdLength.value) if hasattr(domain, "minPwdLength") and domain.minPwdLength.value else 0
        history = int(domain.pwdHistoryLength.value) if hasattr(domain, "pwdHistoryLength") and domain.pwdHistoryLength.value else 0
        lockout = int(domain.lockoutThreshold.value) if hasattr(domain, "lockoutThreshold") and domain.lockoutThreshold.value else 0

        # maxPwdAge: ldap3 may return timedelta (parsed) or int (raw 100-ns intervals)
        max_age_days = None
        if hasattr(domain, "maxPwdAge") and domain.maxPwdAge.value:
            raw = domain.maxPwdAge.value
            import datetime
            if isinstance(raw, datetime.timedelta):
                max_age_days = abs(raw.days) if raw.days != 0 else None
            else:
                raw = int(raw)
                if raw < 0:
                    max_age_days = abs(raw) // (10_000_000 * 86400)
                    if max_age_days == 0:
                        max_age_days = None

        return {
            "min_length": min_length,
            "history": history,
            "lockout": lockout,
            "max_age_days": max_age_days,
        }

    async def _get_password_policy_ldap(self) -> Dict[str, Any]:
        """
        Password policy OpenLDAP via ppolicy overlay.
        Si ppolicy n'est pas configure, retourne defaults.
        """
        try:
            entries = self._search(
                "(objectClass=pwdPolicy)",
                ["pwdMinLength", "pwdInHistory", "pwdMaxFailure",
                 "pwdMaxAge", "pwdLockout"],
            )
            if entries:
                policy = entries[0]
                min_length = int(policy.pwdMinLength.value) if hasattr(policy, "pwdMinLength") and policy.pwdMinLength.value else 0
                history = int(policy.pwdInHistory.value) if hasattr(policy, "pwdInHistory") and policy.pwdInHistory.value else 0
                lockout = int(policy.pwdMaxFailure.value) if hasattr(policy, "pwdMaxFailure") and policy.pwdMaxFailure.value else 0
                max_age_seconds = int(policy.pwdMaxAge.value) if hasattr(policy, "pwdMaxAge") and policy.pwdMaxAge.value else 0
                max_age_days = max_age_seconds // 86400 if max_age_seconds > 0 else None
                return {
                    "min_length": min_length,
                    "history": history,
                    "lockout": lockout,
                    "max_age_days": max_age_days,
                }
        except Exception as e:
            logger.debug(f"ppolicy not available: {e}")

        return self._default_password_policy()

    def _default_password_policy(self) -> Dict[str, Any]:
        """Defaults quand aucune policy n'est lisible."""
        return {
            "min_length": 0,
            "history": 0,
            "lockout": 0,
            "max_age_days": None,
        }

    async def get_admin_summary(self) -> Dict[str, Any]:
        """Compteurs agreges comptes privilegies."""
        await self._connect()

        admin_dns = set()
        admin_groups_found = []

        for pattern in _ADMIN_GROUP_PATTERNS:
            # Escape special chars for LDAP filter
            safe_pattern = pattern.replace("(", "\\28").replace(")", "\\29")
            entries = self._search(
                f"(cn={safe_pattern})",
                ["member", "cn"],
            )
            if entries:
                group = entries[0]
                cn = str(group.cn)
                members = group.member.values if hasattr(group, "member") and group.member.values else []
                # Exclude admin placeholder
                real = [m for m in members if not m.startswith("cn=admin,")]
                admin_dns.update(m.lower() for m in real)
                if real:
                    admin_groups_found.append(cn)

        total_admins = len(admin_dns)

        # Get total users for ratio
        if self._is_ad:
            all_users = self._search(
                "(&(objectClass=user)(!(objectClass=computer)))",
                ["sAMAccountName"],
            )
        else:
            all_users = self._search(
                "(objectClass=inetOrgPerson)",
                ["uid"],
            )
        total_users = len(all_users)
        admin_ratio = round(total_admins / total_users, 4) if total_users > 0 else 0.0

        return {
            "total_admins": total_admins,
            "admin_ratio": admin_ratio,
            "admin_groups": admin_groups_found,
        }

    async def _close_connection(self):
        """Fermeture connexion LDAP."""
        if self.connection:
            try:
                self.connection.unbind()
            except Exception:
                pass
