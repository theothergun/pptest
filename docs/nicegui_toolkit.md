# NiceGUI Toolkit (optional, dev-only)

This project can use `niceguiToolkit` with NiceGUI 3.x in an unsupported mode.

Current setup:
- Keep `nicegui` on latest 3.x.
- Install toolkit without dependency resolution to avoid downgrading NiceGUI.

Install in this project venv:

```powershell
.\.venv\Scripts\python -m pip install niceguiToolkit==0.3.0 --no-deps executing==2.2.1 asttokens==2.4.1
```

Enable at runtime (off by default):

```powershell
$env:NICEGUI_TOOLKIT_ENABLED = "1"
.\.venv\Scripts\python main.py
```

Disable again:

```powershell
Remove-Item Env:NICEGUI_TOOLKIT_ENABLED
```

Notes:
- Integration is guarded in `main.py` and only activates when `NICEGUI_TOOLKIT_ENABLED` is truthy (`1/true/yes/on`).
- `niceguiToolkit` officially targets NiceGUI 2.x (`<3`), so treat this as best-effort dev tooling.
