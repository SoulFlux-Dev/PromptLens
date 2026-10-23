# PromptLens: CMMC 2.0 and NIST SP 800-171 Workplace Compliance & Security Deployment Guide

## 1. Executive Summary & Purpose

PromptLens is an enterprise-grade multimodal screen capture, annotation, and voice-assisted notation suite designed to operate securely within defense industrial base (DIB), federal contracting, and regulated aerospace workplace environments.

When deployed in environments handling Controlled Unclassified Information (CUI) or Covered Defense Information (CDI), software tools must adhere to strict boundary protection, data-at-rest protection, and configuration management controls. PromptLens provides native enterprise controls designed to support compliance with:
- **CMMC 2.0 Level 2 (Advanced / Prioritized)**
- **NIST SP 800-171 Rev 2 (Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations)**
- **DFARS 252.204-7012 (Safeguarding Covered Defense Information and Cyber Incident Reporting)**

By activating Enterprise Air-Gapped Mode (`AirGappedMode=true`), PromptLens operates entirely offline with zero cloud network egress, local-only speech-to-text transcription (via embedded Whisper models), fixed local disk storage with cloud-sync detection, local IPC interface lockdown, and BitLocker volume encryption verification.

---

## 2. NIST SP 800-171 Rev 2 & CMMC 2.0 Security Control Matrix

The table below details how PromptLens architecture and configuration options satisfy specific security controls:

| NIST SP 800-171 Rev 2 Control | CMMC 2.0 Level 2 Practice | Control Title | PromptLens Technical Enforcement |
|---|---|---|---|
| **3.1.20** | **AC.L2-3.1.20** | External Connections | Cloud Egress Killswitch blocks all external network calls; disabled update checks; offline-only operation. |
| **3.13.1** | **SC.L2-3.13.1** | Boundary Protection | Architectural denial of outbound sockets; zero telemetry; zero external API dispatching. |
| **3.13.2** | **SC.L2-3.13.2** | Security Architecture | Principle of least privilege; local-first processing; isolated temporary files cleaned on exit. |
| **3.13.6** | **SC.L2-3.13.6** | Deny Traffic by Default | Egress killswitch in UI and API dispatcher (`llm_api_dispatcher.py`) denies all network transit by default. |
| **3.8.3** | **MP.L2-3.8.3** | Media Protection | Prohibits writing media to commercial cloud sync folders (OneDrive, Dropbox, Google Drive, Box, iCloud). |
| **3.13.16** | **SC.L2-3.13.16** | Data at Rest Protection | Diagnostic self-test verifies BitLocker volume encryption (`audit_bitlocker_volume_encryption()`). |
| **3.4.1** | **CM.L2-3.4.1** | Baseline Configuration | Enterprise configuration lock via `config.ini`; GPO deployment; portable zero-registry footprint. |
| **3.4.2** | **CM.L2-3.4.2** | Security Configuration Settings | Dedicated enterprise code signing (`tools/Sign-Binaries.ps1`) for Windows AppLocker and WDAC whitelisting. |
| **3.1.1** | **AC.L2-3.1.1** | Access Control & Local Interfaces | `DisableLocalIPC=true` shuts down local HTTP webhook server (port 17890) to prevent cross-process snooping. |

---

## 3. Enterprise Air-Gapped Configuration (`config.ini`)

To deploy PromptLens in a compliant air-gapped workplace, place a standardized `config.ini` in the application root directory alongside `QuickClip.exe` and `NotationEditor.exe`.

### Mandatory Enterprise Baseline Configuration:

```ini
[Settings]
OutputDir=C:\SecureNotations\Captures
VideoHotkey=#h
QuickSnipHotkey=PrintScreen
AnnotateHotkey=+PrintScreen
HudToggleHotkey=^+h
ShowRecordingHUD=true
RecordMode=toggle
Microphone=auto
CaptureMode=window
FPS=30
CRF=23
RevertHotkey=!F10
AirGappedMode=true

[Setup]
Completed=true

[Meta]
ConfigVersion=2

[Enterprise]
; Master Air-Gap Switch: Enables full zero-cloud lockdown
AirGappedMode=true

; Redundant Lockdown Directives
ZeroCloudLockdown=true
DisableCloudAPIs=true
DisableUpdateCheck=true
DisableTelemetry=true
LocalOnlyTranscription=true
AllowLocalNetwork=false
DisableLocalIPC=true
EnforceLocalStorage=true
ComplianceProfile=CMMC-L2
AuditLogging=true
```

### Key Security Flags Explained:

- **`AirGappedMode=true`**: Master switch. When active, all cloud endpoints are disabled, the UI displays `[🔒 Air-Gapped Mode]` in the window title, the AI dispatch button is locked in a disabled state, and all background update checks are skipped.
- **`DisableCloudAPIs=true`**: Guarantees that even if an operator attempts to trigger AI assistance, `llm_api_dispatcher.py` throws `CloudEgressBlockedError` and refuses socket creation.
- **`DisableLocalIPC=true`**: Shuts down the internal HTTP server on `127.0.0.1:17890`. In shared workstation or multi-tenant terminal server environments, this prevents other local unprivileged processes from querying recording state or injecting hotkeys.
- **`EnforceLocalStorage=true`**: Activates storage boundary auditing. If an output directory resolves inside a known cloud synchronization path (e.g. OneDrive or Dropbox), PromptLens issues an audit warning and logs a compliance violation.

---

## 4. Packaging, Deployment & Group Policy Automation

PromptLens is distributed as standalone native binaries (`QuickClip.exe`, `NotationEditor.exe`) or a unified enterprise installer (`PromptLens-Setup.exe`).

### 4.1 Silent Installation via Intune / MECM / SCCM

Run the installer silently using Inno Setup standard enterprise flags:

```powershell
PromptLens-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR="C:\Program Files\PromptLens"
```

### 4.2 Group Policy (GPO) Deployment Workflow

1. **Deploy Software Package**: Install `PromptLens` into `%ProgramFiles%\PromptLens\`.
2. **Push Centralized `config.ini`**: Use Group Policy Preferences (GPP) Files policy to copy the pre-configured `config.ini` to `%ProgramFiles%\PromptLens\config.ini` or `%APPDATA%\PromptLens\config.ini`.
3. **Set NTFS Permissions**: Ensure regular standard users have Read & Execute permissions only on `config.ini` to prevent tampering with `AirGappedMode` settings.
4. **Configure Local Media Storage**: Point `OutputDir` to a designated BitLocker-encrypted local volume (e.g. `D:\Notations` or `%USERPROFILE%\Notations`).

---

## 5. Application Whitelisting: AppLocker & Windows Defender Application Control (WDAC)

In compliance with **NIST SP 800-171 Control 3.4.2**, all PromptLens binaries can be signed with an enterprise private code-signing certificate using the built-in signing tool:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File tools/Sign-Binaries.ps1 `
    -CertPath "C:\Certs\EnterpriseCodeSign.pfx" `
    -CertPassword "SecretPassphrase" `
    -WorkspaceRoot "C:\Program Files\PromptLens"
```

### AppLocker Rule Creation:

1. Open `secpol.msc` -> **Application Control Policies** -> **AppLocker** -> **Executable Rules**.
2. Create a **Publisher Rule** matching your enterprise code-signing certificate subject:
   - Publisher: `CN=Your Organization Name, O=Defense Contractor Inc`
   - Product Name: `PromptLens`
   - Minimum Version: `2.0.0.0`
3. Alternatively, create a **Hash Rule** against `bin\QuickClip.exe` and `bin\NotationEditor.exe`.

---

## 6. Security Verification & Compliance Audit

Administrators can verify compliance posture at any time using the automated diagnostic self-test CLI:

```powershell
python src/diagnostic_self_test.py --json
```

### Verification Checklist:

- [x] **Air-Gapped Mode Verification**: Confirm `AirGappedMode: true` and `ZeroCloudLockdown: true`.
- [x] **Cloud Egress Killswitch**: Run `python -m pytest tests/test_cloud_egress_killswitch.py` to confirm zero egress.
- [x] **BitLocker Encryption Verification**: Confirm volume hosting `OutputDir` reports `ProtectionStatus: 1` (Encrypted).
- [x] **Local IPC Webhook Disabled**: Verify no socket listening on `127.0.0.1:17890`.
- [x] **Storage Path Verification**: Confirm output folder does not reside in cloud-synced folders.
- [x] **Code Signature Verification**: Run `Get-AuthenticodeSignature bin\QuickClip.exe` to confirm `Valid` signature status.

---

## 7. Incident Handling & Audit Trail

PromptLens maintains local audit logs when `AuditLogging=true`. Logs are written to `%APPDATA%\PromptLens\logs\` or the configured `OutputDir\logs\`.
- All blocked cloud egress attempts are recorded with timestamp and reason.
- Storage boundary compliance warnings are logged upon startup and folder selection.
- No audio recordings or image captures are ever transmitted beyond the physical host machine.
