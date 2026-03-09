# NOX Packaging - Operator Guide

This guide explains the NOX packaging screens in simple, operator-focused steps.

## 1. Operator View (Packaging NOX)

Screen file:
- `pages/operator/packaging/packaging_nox.py`

Related runtime scripts:
- `scripts/itac/packaging/pack_twincat.py`
- `scripts/itac/packaging/container_scan.py`
- `scripts/itac/packaging/container_update.py`

### What you see on this screen
- Current serial number
- Good counter
- Bad counter
- Active container information
- Current quantity and max quantity
- Instruction for worker
- Current step / feedback
- Buttons: `Start`, `Stop`, `Reset`, `Refresh`

### Normal operator flow
1. Check device status in the feedback area.
2. Scan or load a valid packaging container.
3. Press `Start`.
4. Process parts as instructed.
5. Watch counters and feedback messages.
6. If needed, press `Stop`.
7. Use `Refresh` after container changes.

### Button meaning
- `Start`: starts machine automatic flow.
- `Stop`: stops machine automatic flow.
- `Reset`: sends PLC reset pulse and refreshes container info.
- `Refresh`: reloads current container and pack info.

### Important behavior
- If PLC or scanner is disconnected, the system shows warning/error feedback and blocks normal run behavior.
- If container is full, the system stops automatic mode and asks for a new container.
- MES-related PLC error codes are translated to readable iTAC error text when possible.

### Screenshot placeholders
- `[Screenshot Placeholder - Packaging NOX main screen]`
- `[Screenshot Placeholder - Start/Stop area]`
- `[Screenshot Placeholder - Container full message]`

---

## 2. Container Management

Screen file:
- `pages/operator/packaging/container_management.py`

Related runtime script:
- `scripts/itac/packaging/container_management.py`

### What you can do
- Search container by container number
- Search container by serial number
- Activate selected container
- List serials in selected container
- Remove one selected serial (with confirmation)

### Normal operator flow
1. Enter search text.
2. Click `Search by container` or `Search by Serialnumber`.
3. Select a container row.
4. Click `Activate` if this container should be active.
5. Click `Search` in serial section to load serial numbers.
6. Select a serial row.
7. Click `Remove Serial` only if removal is required.

### Notes for operators
- `Remove Serial` is only enabled when a container is selected.
- Removal and activation require confirmation dialogs.
- `Remove All` and `Refresh` are hidden in current runtime behavior.

### Screenshot placeholders
- `[Screenshot Placeholder - Container search results]`
- `[Screenshot Placeholder - Serial list section]`
- `[Screenshot Placeholder - Activate confirmation popup]`

---

## 3. Packaging NOX Status (TwinCAT Status Page)

Screen file:
- `pages/operator/packaging_nox_status.py`

### What this page is for
- Live engineering/diagnostic view of TwinCAT variables from `NOX_Packaging` configuration.
- Variables are grouped by machine area to make status checks faster.
- Read-only tags are shown as read-only.
- Writable tags can be edited and written from the page.

### Typical usage
1. Open the status page.
2. Check PLC connection badge.
3. Open the relevant group (MES, Stepchain, IO, Cameras, Fixture).
4. Verify live values.
5. For writable tags, use `Use` to load current value, then `Write` to send a value.

### Safety note
- Only write values when instructed by maintenance/process engineering.
- Wrong writes can stop production or cause machine faults.

### Screenshot placeholders
- `[Screenshot Placeholder - Status page overview]`
- `[Screenshot Placeholder - Grouped TwinCAT variables]`
- `[Screenshot Placeholder - Writable variable write action]`

---

## Quick Troubleshooting

- `PLC disconnected`:
  Check Beckhoff connection and network.
- `Scanner disconnected`:
  Check scanner power/network and TCP client status.
- `Container full`:
  Scan and activate a new container.
- `MES/iTAC error`:
  Read feedback text and inform support with exact message.

---

## Script Folder Reference

All NOX packaging scripts mentioned above are in:
- `scripts/itac/packaging`

Main files:
- `pack_twincat.py`
- `container_scan.py`
- `container_update.py`
- `container_management.py`
- `reset_serialnumbers.py` (service/maintenance use)
- `serialnumber.py` (test/example behavior)
