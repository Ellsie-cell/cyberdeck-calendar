# Cyberdeck Calendar // Privacy-First Desktop HUD

A floating cyber-glass desktop calendar and scheduling HUD built for the Cyberdeck ecosystem. Integrates Aura CRM and Aura TPRM streams without overlapping or mutating databases, featuring dual-layer glance privacy, RFC 5545 Proton Calendar export, and Work_Hub tray controls.

## Features
- **Dual-Layer Privacy Model**:
  - *Ambient Glance Mode*: Default screen-glance safe state displaying abstracted status pills (`[◈ CRM]`, `[⏣ TPRM]`, `[● OPS]`). Zero client names or contract terms exposed to shoulder-surfers.
  - *Deep Workflow Drawer*: Clicking any event smoothly expands a detailed cyberdeck dossier with client info, contract deliverables, and direct actions (`[◈ Open in Aura CRM]`, `[⏣ Audit in TPRM]`, `[Export to Proton]`).
- **Strict Non-Overlapping Streams**:
  - Read-only adapters for Aura CRM (`aura_network.vault`) and Aura TPRM (`tprm_vault.db`).
  - Isolated GUID namespaces (`crm-*`, `tprm-*`, `ops-*`).
- **Proton Calendar RFC 5545 Export**:
  - One-click `.ics` export with standard UIDs, timestamps, and 15-minute popup alarms.
- **Floating HUD Architecture**:
  - GTK3 + WebKit2 transparent compositing matching Hana Companion Hub.
  - Geometry memory in `~/.config/cyberdeck/calendar_geometry.json`.
  - Single-instance UNIX socket control (`--toggle`, `--show`, `--hide`, `--quit`).
- **Work_Hub Tray Integration**:
  - Launches directly from the Work_Hub tray menu alongside Hana Hub.

## Usage
```bash
cyberdeck-calendar          # Launch or present calendar HUD
cyberdeck-calendar --toggle # Toggle visibility from hotkey or tray
cyberdeck-calendar --show   # Bring HUD to front
cyberdeck-calendar --hide   # Hide HUD
cyberdeck-calendar --export-ics # Non-interactive CLI Proton export
```
