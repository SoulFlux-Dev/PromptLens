"""
Enterprise Air-Gapped configuration schema and zero-cloud lockdown manager for PromptLens (ENT-003).
Provides enterprise configuration loading, schema validation, CMMC 2.0 / NIST SP 800-171
compliance auditing, air-gap policy enforcement, and zero-cloud egress lockdown.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from portable_mode import resolve_config_path
except ImportError:
    try:
        from .portable_mode import resolve_config_path
    except Exception:
        resolve_config_path = None

try:
    from offline_privacy_guard import get_offline_privacy_status
except ImportError:
    try:
        from .offline_privacy_guard import get_offline_privacy_status
    except Exception:
        get_offline_privacy_status = None


ENTERPRISE_SECTION = "Enterprise"

COMPLIANCE_PROFILES = (
    "CMMC-L2",
    "NIST-SP-800-171",
    "HIPAA",
    "AIR-GAPPED-DEFENSE",
    "NONE",
    "CUSTOM",
)

CLOUD_SYNC_SIGNATURES = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud",
    "iclouddrive",
    "box sync",
    "nextcloud",
    "owncloud",
    "synologydrive",
)

# NIST SP 800-171 Rev 2 and CMMC 2.0 Level 2 Security Control Mappings
NIST_CMMC_CONTROLS = {
    "NIST-3.1.20": {
        "title": "Verify and control external connections",
        "cmmc_practice": "AC.L2-3.1.20",
        "description": "Verify and control/limit connections to external systems and public networks.",
    },
    "NIST-3.13.1": {
        "title": "Boundary Protection",
        "cmmc_practice": "SC.L2-3.13.1",
        "description": "Monitor, control, and protect communications at external boundaries and key internal boundaries.",
    },
    "NIST-3.13.2": {
        "title": "Security Architecture Principles",
        "cmmc_practice": "SC.L2-3.13.2",
        "description": "Employ architectural designs and software engineering principles promoting zero-trust isolation.",
    },
    "NIST-3.13.6": {
        "title": "Deny Communications Traffic by Default",
        "cmmc_practice": "SC.L2-3.13.6",
        "description": "Deny network communications traffic by default and allow network communications traffic by exception.",
    },
    "NIST-3.8.3": {
        "title": "Local Storage & Media Protection",
        "cmmc_practice": "MP.L2-3.8.3",
        "description": "Prevent unauthorized offloading or synchronization of sensitive media to commercial cloud storage.",
    },
}

DEFAULT_ENTERPRISE_SETTINGS: Dict[str, str] = {
    "AirGappedMode": "false",
    "ZeroCloudLockdown": "false",
    "DisableCloudAPIs": "false",
    "DisableUpdateCheck": "false",
    "DisableTelemetry": "true",
    "LocalOnlyTranscription": "true",
    "AllowLocalNetwork": "true",
    "DisableLocalIPC": "false",
    "EnforceLocalStorage": "true",
    "ComplianceProfile": "CMMC-L2",
    "AuditLogging": "true",
}


@dataclass
class EnterpriseConfig:
    """
    Enterprise Air-Gapped and Zero-Cloud configuration model.
    Represents the schema in config.ini [Enterprise] section.
    """
    air_gapped_mode: bool = False
    zero_cloud_lockdown: bool = False
    disable_cloud_apis: bool = False
    disable_update_check: bool = False
    disable_telemetry: bool = True
    local_only_transcription: bool = True
    allow_local_network: bool = True
    disable_local_ipc: bool = False
    enforce_local_storage: bool = True
    compliance_profile: str = "CMMC-L2"
    audit_logging: bool = True

    @property
    def is_air_gapped(self) -> bool:
        """Returns True if air-gapped isolation mode is active."""
        return self.air_gapped_mode

    @property
    def is_zero_cloud_lockdown(self) -> bool:
        """Returns True if zero-cloud lockdown is in effect (either explicitly or via air-gapped mode)."""
        return self.air_gapped_mode or self.zero_cloud_lockdown

    @property
    def is_cloud_egress_blocked(self) -> bool:
        """Returns True if all cloud network egress is prohibited."""
        return self.air_gapped_mode or self.zero_cloud_lockdown or self.disable_cloud_apis

    @property
    def is_cloud_api_allowed(self) -> bool:
        """Returns True if remote LLM / vision cloud APIs may be invoked."""
        return not self.is_cloud_egress_blocked

    @property
    def is_update_check_allowed(self) -> bool:
        """Returns True if external update checking via GitHub Releases API is allowed."""
        if self.air_gapped_mode or self.zero_cloud_lockdown or self.disable_update_check:
            return False
        return True

    @property
    def is_telemetry_disabled(self) -> bool:
        """Returns True if telemetry and analytics reporting is disabled."""
        return self.disable_telemetry or self.air_gapped_mode or self.zero_cloud_lockdown

    @property
    def is_local_only_transcription_enforced(self) -> bool:
        """Returns True if transcription must run 100% on local hardware with zero cloud offloading."""
        return self.local_only_transcription or self.air_gapped_mode or self.zero_cloud_lockdown

    @property
    def is_local_network_allowed(self) -> bool:
        """Returns True if local loopback or private subnet connections are allowed."""
        return self.allow_local_network

    @property
    def is_local_ipc_allowed(self) -> bool:
        """Returns True if local IPC webhook server is permitted to listen."""
        return self.allow_local_network and not self.disable_local_ipc

    @property
    def is_local_storage_enforced(self) -> bool:
        """Returns True if recording and notation output must remain on local fixed storage."""
        return self.enforce_local_storage or self.air_gapped_mode or self.zero_cloud_lockdown

    def to_dict(self) -> Dict[str, Any]:
        """Serializes configuration to python dictionary with native types."""
        return asdict(self)

    def to_ini_dict(self) -> Dict[str, str]:
        """Serializes configuration to INI string key-values."""
        return {
            "AirGappedMode": "true" if self.air_gapped_mode else "false",
            "ZeroCloudLockdown": "true" if self.zero_cloud_lockdown else "false",
            "DisableCloudAPIs": "true" if self.disable_cloud_apis else "false",
            "DisableUpdateCheck": "true" if self.disable_update_check else "false",
            "DisableTelemetry": "true" if self.disable_telemetry else "false",
            "LocalOnlyTranscription": "true" if self.local_only_transcription else "false",
            "AllowLocalNetwork": "true" if self.allow_local_network else "false",
            "DisableLocalIPC": "true" if self.disable_local_ipc else "false",
            "EnforceLocalStorage": "true" if self.enforce_local_storage else "false",
            "ComplianceProfile": self.compliance_profile,
            "AuditLogging": "true" if self.audit_logging else "false",
        }


def _bool_from_str(val: Any, default: bool = False) -> bool:
    """Helper to safely parse boolean string representations."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on", "enable", "enabled"):
        return True
    if s in ("false", "0", "no", "off", "disable", "disabled"):
        return False
    return default


def validate_enterprise_setting(key: str, value: Any) -> Tuple[bool, str]:
    """
    Validates an enterprise setting key and value.
    Returns (is_valid, sanitized_value_string).
    """
    if key not in DEFAULT_ENTERPRISE_SETTINGS:
        return False, str(value) if value is not None else ""

    if value is None:
        return False, DEFAULT_ENTERPRISE_SETTINGS[key]

    val_str = str(value).strip()

    boolean_keys = (
        "AirGappedMode",
        "ZeroCloudLockdown",
        "DisableCloudAPIs",
        "DisableUpdateCheck",
        "DisableTelemetry",
        "LocalOnlyTranscription",
        "AllowLocalNetwork",
        "DisableLocalIPC",
        "EnforceLocalStorage",
        "AuditLogging",
    )

    if key in boolean_keys:
        low = val_str.lower()
        if low in ("true", "1", "yes", "on", "enable", "enabled"):
            return True, "true"
        if low in ("false", "0", "no", "off", "disable", "disabled"):
            return True, "false"
        return False, DEFAULT_ENTERPRISE_SETTINGS[key]

    if key == "ComplianceProfile":
        for prof in COMPLIANCE_PROFILES:
            if val_str.upper() == prof.upper():
                return True, prof
        # Accept custom string if alphanumeric/hyphen
        if val_str and all(c.isalnum() or c in ("-", "_") for c in val_str):
            return True, val_str.upper()
        return False, "CMMC-L2"

    return True, val_str


def resolve_config_file(config_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Resolves the configuration file path.
    Uses provided path, portable_mode resolver, or falls back to 'config.ini'.
    """
    if config_path:
        return Path(config_path).resolve()

    if resolve_config_path is not None:
        try:
            return Path(resolve_config_path()).resolve()
        except Exception:
            pass

    return Path("config.ini").resolve()


def load_enterprise_config(config_path: Optional[Union[str, Path]] = None) -> EnterpriseConfig:
    """
    Loads Enterprise configuration from config.ini.
    Gracefully handles missing sections, corrupted keys, and falls back to safe defaults.
    Also checks [Settings] for AirGappedMode if not present in [Enterprise].
    """
    target = resolve_config_file(config_path)
    cfg = configparser.ConfigParser()

    if target.is_file():
        try:
            cfg.read(target, encoding="utf-8")
        except Exception:
            # File unparseable; return default model
            return EnterpriseConfig()

    has_ent = cfg.has_section(ENTERPRISE_SECTION)
    has_set = cfg.has_section("Settings")

    # AirGappedMode resolution (checks [Enterprise] first, then [Settings])
    raw_airgap = None
    if has_ent and cfg.has_option(ENTERPRISE_SECTION, "AirGappedMode"):
        raw_airgap = cfg.get(ENTERPRISE_SECTION, "AirGappedMode")
    elif has_set and cfg.has_option("Settings", "AirGappedMode"):
        raw_airgap = cfg.get("Settings", "AirGappedMode")
    air_gapped_mode = _bool_from_str(raw_airgap, default=False)

    def get_bool(key: str, default: bool) -> bool:
        if has_ent and cfg.has_option(ENTERPRISE_SECTION, key):
            return _bool_from_str(cfg.get(ENTERPRISE_SECTION, key), default)
        return default

    def get_str(key: str, default: str) -> str:
        if has_ent and cfg.has_option(ENTERPRISE_SECTION, key):
            val = cfg.get(ENTERPRISE_SECTION, key).strip()
            valid, sanitized = validate_enterprise_setting(key, val)
            return sanitized if valid else default
        return default

    return EnterpriseConfig(
        air_gapped_mode=air_gapped_mode,
        zero_cloud_lockdown=get_bool("ZeroCloudLockdown", False),
        disable_cloud_apis=get_bool("DisableCloudAPIs", False),
        disable_update_check=get_bool("DisableUpdateCheck", False),
        disable_telemetry=get_bool("DisableTelemetry", True),
        local_only_transcription=get_bool("LocalOnlyTranscription", True),
        allow_local_network=get_bool("AllowLocalNetwork", True),
        disable_local_ipc=get_bool("DisableLocalIPC", False),
        enforce_local_storage=get_bool("EnforceLocalStorage", True),
        compliance_profile=get_str("ComplianceProfile", "CMMC-L2"),
        audit_logging=get_bool("AuditLogging", True),
    )


def save_enterprise_config(
    config: EnterpriseConfig,
    config_path: Optional[Union[str, Path]] = None
) -> bool:
    """
    Saves the Enterprise configuration to config.ini, preserving existing sections and comments.
    Returns True if successfully written.
    """
    target = resolve_config_file(config_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    cfg = configparser.ConfigParser()
    if target.is_file():
        try:
            cfg.read(target, encoding="utf-8")
        except Exception:
            cfg = configparser.ConfigParser()

    if not cfg.has_section(ENTERPRISE_SECTION):
        cfg.add_section(ENTERPRISE_SECTION)

    ini_dict = config.to_ini_dict()
    for k, v in ini_dict.items():
        cfg.set(ENTERPRISE_SECTION, k, v)

    # Ensure AirGappedMode is mirrored in [Settings] if [Settings] exists for compatibility
    if cfg.has_section("Settings"):
        cfg.set("Settings", "AirGappedMode", "true" if config.air_gapped_mode else "false")

    temp_file = target.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            cfg.write(f)
        temp_file.replace(target)
        return True
    except OSError:
        if temp_file.is_file():
            try:
                temp_file.unlink()
            except OSError:
                pass
        return False


def update_enterprise_setting(
    key: str,
    value: Any,
    config_path: Optional[Union[str, Path]] = None
) -> bool:
    """
    Updates a single enterprise setting in config.ini.
    """
    valid, sanitized = validate_enterprise_setting(key, value)
    if not valid:
        return False

    current_config = load_enterprise_config(config_path)
    prop_name = _setting_key_to_attr(key)
    if not hasattr(current_config, prop_name):
        return False

    bool_keys = (
        "AirGappedMode",
        "ZeroCloudLockdown",
        "DisableCloudAPIs",
        "DisableUpdateCheck",
        "DisableTelemetry",
        "LocalOnlyTranscription",
        "AllowLocalNetwork",
        "DisableLocalIPC",
        "EnforceLocalStorage",
        "AuditLogging",
    )

    if key in bool_keys:
        setattr(current_config, prop_name, _bool_from_str(sanitized))
    else:
        setattr(current_config, prop_name, sanitized)

    return save_enterprise_config(current_config, config_path)


def enable_air_gapped_mode(
    config_path: Optional[Union[str, Path]] = None,
    profile: str = "CMMC-L2",
    disable_ipc: Optional[bool] = None,
) -> EnterpriseConfig:
    """
    Enforces strict air-gapped zero-cloud lockdown on the configuration.
    Sets AirGappedMode=true, ZeroCloudLockdown=true, DisableCloudAPIs=true,
    DisableUpdateCheck=true, and saves to config.ini.
    For high-security environments (AIR-GAPPED-DEFENSE or disable_ipc=True),
    also disables local IPC webhook interface (ENT-005).
    """
    config = load_enterprise_config(config_path)
    config.air_gapped_mode = True
    config.zero_cloud_lockdown = True
    config.disable_cloud_apis = True
    config.disable_update_check = True
    config.disable_telemetry = True
    config.local_only_transcription = True
    config.enforce_local_storage = True
    config.compliance_profile = profile
    config.audit_logging = True

    if disable_ipc is not None:
        config.disable_local_ipc = bool(disable_ipc)
    elif profile.upper() in ("AIR-GAPPED-DEFENSE", "HIGH-SECURITY"):
        config.disable_local_ipc = True

    save_enterprise_config(config, config_path)
    return config


def disable_air_gapped_mode(
    config_path: Optional[Union[str, Path]] = None
) -> EnterpriseConfig:
    """
    Deactivates air-gapped mode, restoring standard local/cloud operational state.
    """
    config = load_enterprise_config(config_path)
    config.air_gapped_mode = False
    config.zero_cloud_lockdown = False
    config.disable_cloud_apis = False
    config.disable_update_check = False
    config.disable_local_ipc = False
    save_enterprise_config(config, config_path)
    return config


def is_air_gapped_mode(config_path: Optional[Union[str, Path]] = None) -> bool:
    """Quick helper: Returns True if active configuration has AirGappedMode enabled."""
    return load_enterprise_config(config_path).is_air_gapped


def is_zero_cloud_lockdown(config_path: Optional[Union[str, Path]] = None) -> bool:
    """Quick helper: Returns True if active configuration is under zero-cloud lockdown."""
    return load_enterprise_config(config_path).is_zero_cloud_lockdown


def is_cloud_egress_blocked(config_path: Optional[Union[str, Path]] = None) -> bool:
    """Quick helper: Returns True if active configuration blocks cloud egress."""
    return load_enterprise_config(config_path).is_cloud_egress_blocked


def is_cloud_api_allowed(config_path: Optional[Union[str, Path]] = None) -> bool:
    """Quick helper: Returns True if external cloud APIs are permitted."""
    return load_enterprise_config(config_path).is_cloud_api_allowed


def assert_cloud_egress_allowed(config_path: Optional[Union[str, Path]] = None) -> None:
    """
    Asserts that cloud egress is permitted by active enterprise configuration.
    Raises PermissionError if cloud egress is blocked by Enterprise Air-Gapped Zero-Cloud policy.
    """
    if is_cloud_egress_blocked(config_path):
        raise PermissionError(
            "Cloud egress blocked by Enterprise Air-Gapped Zero-Cloud policy."
        )


def is_local_ipc_allowed(config_path: Optional[Union[str, Path]] = None) -> bool:
    """Quick helper: Returns True if local IPC webhook server is permitted to listen (ENT-005)."""
    return load_enterprise_config(config_path).is_local_ipc_allowed


def set_local_ipc_disabled(
    disabled: bool = True,
    config_path: Optional[Union[str, Path]] = None,
) -> EnterpriseConfig:
    """
    Explicit toggle to enable or disable local IPC webhook server for high-security environments (ENT-005).
    """
    config = load_enterprise_config(config_path)
    config.disable_local_ipc = bool(disabled)
    save_enterprise_config(config, config_path)
    return config


def enable_local_ipc(config_path: Optional[Union[str, Path]] = None) -> EnterpriseConfig:
    """Enables local IPC webhook interface."""
    return set_local_ipc_disabled(False, config_path)


def disable_local_ipc(config_path: Optional[Union[str, Path]] = None) -> EnterpriseConfig:
    """Disables local IPC webhook interface for high-security environments."""
    return set_local_ipc_disabled(True, config_path)


def validate_storage_location_compliance(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Validates whether an output directory complies with enterprise air-gapped media storage rules.
    Detects if path resides in commercial cloud sync folders (OneDrive, Dropbox, Google Drive, Box).
    """
    norm_path = str(Path(path).resolve()).lower()
    detected_syncs = [sig for sig in CLOUD_SYNC_SIGNATURES if sig in norm_path]

    is_compliant = len(detected_syncs) == 0
    return {
        "is_compliant": is_compliant,
        "path": str(path),
        "detected_cloud_sync": detected_syncs if detected_syncs else None,
        "warning": (
            f"Path '{path}' appears to be within a cloud-synchronized folder ({', '.join(detected_syncs)}). "
            "Air-gapped enterprise compliance requires local-only fixed disk storage."
            if not is_compliant else None
        )
    }


def get_enterprise_compliance_report(
    config_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Performs a comprehensive CMMC 2.0 Level 2 and NIST SP 800-171 Rev 2
    compliance audit of current configuration settings.
    """
    config = load_enterprise_config(config_path)
    cfg_file = resolve_config_file(config_path)

    # Storage check
    target_dir = output_dir or os.getcwd()
    storage_check = validate_storage_location_compliance(target_dir)

    # Privacy status check
    privacy_info = {}
    if get_offline_privacy_status is not None:
        try:
            privacy_info = get_offline_privacy_status()
        except Exception:
            pass

    # Evaluate controls
    controls_evaluated: Dict[str, Dict[str, Any]] = {}

    # Control 1: AC.L2-3.1.20 / NIST 3.1.20 (External Connections)
    c1_pass = config.is_cloud_egress_blocked and not config.is_update_check_allowed
    controls_evaluated["NIST-3.1.20"] = {
        "cmmc_id": "AC.L2-3.1.20",
        "title": NIST_CMMC_CONTROLS["NIST-3.1.20"]["title"],
        "status": "PASS" if c1_pass else ("FAIL" if config.air_gapped_mode else "WARNING"),
        "details": (
            "Cloud egress and remote connections strictly blocked."
            if c1_pass else "External cloud API egress or update checks are permitted."
        )
    }

    # Control 2: SC.L2-3.13.1 / NIST 3.13.1 (Boundary Protection)
    c2_pass = config.is_zero_cloud_lockdown
    controls_evaluated["NIST-3.13.1"] = {
        "cmmc_id": "SC.L2-3.13.1",
        "title": NIST_CMMC_CONTROLS["NIST-3.13.1"]["title"],
        "status": "PASS" if c2_pass else ("FAIL" if config.air_gapped_mode else "WARNING"),
        "details": (
            "Zero-cloud perimeter boundary protection is actively enforced."
            if c2_pass else "Boundary protection allows standard internet outbound traffic."
        )
    }

    # Control 3: SC.L2-3.13.6 / NIST 3.13.6 (Deny Communications by Default)
    c3_pass = config.air_gapped_mode and config.zero_cloud_lockdown
    controls_evaluated["NIST-3.13.6"] = {
        "cmmc_id": "SC.L2-3.13.6",
        "title": NIST_CMMC_CONTROLS["NIST-3.13.6"]["title"],
        "status": "PASS" if c3_pass else ("FAIL" if config.air_gapped_mode else "WARNING"),
        "details": (
            "Air-gapped deny-by-default communication rule active."
            if c3_pass else "Application is operating in standard connected mode."
        )
    }

    # Control 4: MP.L2-3.8.3 / NIST 3.8.3 (Media Storage Protection)
    c4_pass = storage_check["is_compliant"] and config.is_local_storage_enforced
    controls_evaluated["NIST-3.8.3"] = {
        "cmmc_id": "MP.L2-3.8.3",
        "title": NIST_CMMC_CONTROLS["NIST-3.8.3"]["title"],
        "status": "PASS" if c4_pass else "WARNING",
        "details": (
            "Captures and notations stored strictly on local fixed storage."
            if c4_pass else storage_check.get("warning") or "Local storage enforcement not asserted."
        )
    }

    # Voice memo privacy verification
    voice_local_pass = config.is_local_only_transcription_enforced
    controls_evaluated["PRIVACY-STT"] = {
        "cmmc_id": "N/A (Local Only)",
        "title": "Voice Privacy & On-Device Transcription",
        "status": "PASS" if voice_local_pass else "FAIL",
        "details": (
            "Speech recognition executes 100% on local hardware; zero voice audio offloaded."
            if voice_local_pass else "Cloud transcription fallback is permitted."
        )
    }

    # Overall determination
    all_pass = all(c["status"] == "PASS" for c in controls_evaluated.values())
    has_fail = any(c["status"] == "FAIL" for c in controls_evaluated.values())

    if all_pass:
        overall_status = "COMPLIANT"
    elif has_fail:
        overall_status = "NON_COMPLIANT"
    else:
        overall_status = "STANDARD_CONNECTED"

    return {
        "overall_status": overall_status,
        "compliance_profile": config.compliance_profile,
        "config_file": str(cfg_file),
        "air_gapped_mode": config.air_gapped_mode,
        "zero_cloud_lockdown": config.is_zero_cloud_lockdown,
        "cloud_apis_blocked": config.is_cloud_egress_blocked,
        "update_check_blocked": not config.is_update_check_allowed,
        "telemetry_disabled": config.is_telemetry_disabled,
        "local_transcription_only": config.is_local_only_transcription_enforced,
        "local_storage_compliant": storage_check["is_compliant"],
        "local_ipc_allowed": config.is_local_ipc_allowed,
        "local_ipc_disabled": not config.is_local_ipc_allowed,
        "controls": controls_evaluated,
        "privacy_status": privacy_info,
        "settings": config.to_dict(),
    }


def format_enterprise_compliance_report(report: Dict[str, Any]) -> str:
    """
    Formats the enterprise compliance report into a structured, human-readable CLI report.
    """
    lines = [
        "==================================================================",
        "      PromptLens Enterprise Air-Gapped Compliance Audit           ",
        "==================================================================",
        f"Compliance Status : {report.get('overall_status', 'UNKNOWN')}",
        f"Profile Target    : {report.get('compliance_profile', 'CMMC-L2')}",
        f"Configuration File: {report.get('config_file', 'config.ini')}",
        f"Air-Gapped Mode   : {'ENABLED (Lockdown Active)' if report.get('air_gapped_mode') else 'DISABLED (Standard Mode)'}",
        f"Zero-Cloud Policy : {'STRICT ENFORCEMENT' if report.get('zero_cloud_lockdown') else 'STANDARD CONNECTED'}",
        "",
        "--- Security Controls Audit (NIST SP 800-171 / CMMC 2.0) ---",
    ]

    controls = report.get("controls", {})
    for cid, data in controls.items():
        cmmc = data.get("cmmc_practice") or data.get("cmmc_id", "")
        status = data.get("status", "UNKNOWN")
        icon = "[PASS]" if status == "PASS" else ("[WARN]" if status == "WARNING" else "[FAIL]")
        lines.append(f"{icon:<7} {cid:<13} ({cmmc:<14}) : {data.get('title', '')}")
        lines.append(f"        Details: {data.get('details', '')}")

    lines.extend([
        "",
        "--- Subsystem Lockdown State ---",
        f"  - Cloud Vision / LLM APIs   : {'BLOCKED (Zero Egress)' if report.get('cloud_apis_blocked') else 'ALLOWED'}",
        f"  - GitHub Update Checker     : {'BLOCKED' if report.get('update_check_blocked') else 'ALLOWED'}",
        f"  - Remote Telemetry / Stats  : {'DISABLED' if report.get('telemetry_disabled') else 'ENABLED'}",
        f"  - Whisper Transcription Engine: {'LOCAL ONLY (100% On-Device)' if report.get('local_transcription_only') else 'CLOUD ALLOWED'}",
        f"  - Recording Output Storage  : {'LOCAL VOLUME VALIDATED' if report.get('local_storage_compliant') else 'CLOUD SYNC WARNING'}",
        f"  - Local IPC Webhook Server  : {'DISABLED (High-Security Lockdown)' if not report.get('local_ipc_allowed', True) else 'ALLOWED'}",
        "==================================================================",
    ])
    return "\n".join(lines)


def _setting_key_to_attr(key: str) -> str:
    """Converts CamelCase INI setting key to snake_case attribute name."""
    mapping = {
        "AirGappedMode": "air_gapped_mode",
        "ZeroCloudLockdown": "zero_cloud_lockdown",
        "DisableCloudAPIs": "disable_cloud_apis",
        "DisableUpdateCheck": "disable_update_check",
        "DisableTelemetry": "disable_telemetry",
        "LocalOnlyTranscription": "local_only_transcription",
        "AllowLocalNetwork": "allow_local_network",
        "DisableLocalIPC": "disable_local_ipc",
        "EnforceLocalStorage": "enforce_local_storage",
        "ComplianceProfile": "compliance_profile",
        "AuditLogging": "audit_logging",
    }
    return mapping.get(key, key.lower())


def main(args_list: Optional[List[str]] = None) -> int:
    """
    CLI interface for enterprise compliance inspection and air-gapped configuration.
    """
    parser = argparse.ArgumentParser(
        prog="enterprise_config",
        description="PromptLens Enterprise Air-Gapped and Zero-Cloud Configuration Manager.",
    )
    parser.add_argument("--config", "-c", default=None, help="Path to config.ini file")
    parser.add_argument("--status", "-s", action="store_true", help="Display current enterprise configuration")
    parser.add_argument("--audit", "-a", action="store_true", help="Perform NIST SP 800-171 / CMMC 2.0 compliance audit")
    parser.add_argument("--lockdown", "--airgap", action="store_true", help="Activate strict Air-Gapped Zero-Cloud lockdown")
    parser.add_argument("--unlock", action="store_true", help="Deactivate air-gapped mode")
    parser.add_argument("--disable-ipc", action="store_true", help="Disable local IPC webhook server for high-security environments")
    parser.add_argument("--enable-ipc", action="store_true", help="Enable local IPC webhook server")
    parser.add_argument("--profile", default=None, help="Set compliance profile (e.g. CMMC-L2, NIST-SP-800-171)")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args(args_list)

    if args.disable_ipc and not args.lockdown:
        cfg = disable_local_ipc(args.config)
        if args.json:
            print(json.dumps({"status": "ipc_disabled", "disable_local_ipc": True, "config": cfg.to_dict()}, indent=2))
        else:
            print("Local IPC webhook server DISABLED for high-security environments.")
        return 0

    if args.enable_ipc and not args.lockdown:
        cfg = enable_local_ipc(args.config)
        if args.json:
            print(json.dumps({"status": "ipc_enabled", "disable_local_ipc": False, "config": cfg.to_dict()}, indent=2))
        else:
            print("Local IPC webhook server ENABLED.")
        return 0

    if args.lockdown:
        prof = args.profile or "CMMC-L2"
        disable_ipc_flag = True if args.disable_ipc else None
        cfg = enable_air_gapped_mode(args.config, profile=prof, disable_ipc=disable_ipc_flag)
        if args.json:
            print(json.dumps({"status": "locked_down", "config": cfg.to_dict()}, indent=2))
        else:
            ipc_note = " (IPC Server Disabled)" if cfg.disable_local_ipc else ""
            print(f"Enterprise Air-Gapped Zero-Cloud lockdown ENABLED (Profile: {prof}){ipc_note}.")
        return 0

    if args.unlock:
        cfg = disable_air_gapped_mode(args.config)
        if args.json:
            print(json.dumps({"status": "unlocked", "config": cfg.to_dict()}, indent=2))
        else:
            print("Enterprise Air-Gapped mode DISABLED. Standard connected state restored.")
        return 0

    if args.audit or not args.status:
        report = get_enterprise_compliance_report(args.config)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(format_enterprise_compliance_report(report))
        return 0 if report["overall_status"] in ("COMPLIANT", "STANDARD_CONNECTED") else 1

    # Display status
    cfg = load_enterprise_config(args.config)
    if args.json:
        print(json.dumps(cfg.to_dict(), indent=2))
    else:
        print("PromptLens Enterprise Configuration:")
        for k, v in cfg.to_ini_dict().items():
            print(f"  {k:<25} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
