# Quick Start

This quick start is for operators, technicians, and power users who want to run the app and test scripts quickly.

## 1) Install and run

From repository root:

```bash
python main.py
```

Open the shown URL in your browser (default NiceGUI URL is usually `http://localhost:8080`).

## 2) Select config set

The app supports config sets in `config/sets/*.json`.

- Default production-like set: `config/sets/default.json`
- Training set for this guide: `config/sets/training.json`

To switch sets in UI:

1. Open **Settings**.
2. Open **Startup Settings**.
3. Select set `training`.
4. Save and reload the page.

You can also force a config file with env var:

```bash
APP_CONFIG_PATH=config/sets/training.json python main.py
```

## 3) Open Script Lab

1. Open **Settings**.
2. Open **Scripts Lab**.
3. Confirm scripts are listed.

Training scripts are:

- `training/training_example_view_1`
- `training/training_example_view_2`

## 4) Start one training script

In Scripts Lab:

1. Select one training script.
2. Click **Start Chain** (instance id `default` is fine).

> Run only one training script instance for the same view at a time (to avoid conflicting state updates).

## 5) Open training view

Navigate to route **Training Example**.

You can now:

- click training buttons,
- simulate TCP scanner input,
- show popup/confirm dialogs,
- write CSV rows to local disk.

## 6) Where to check output

- CSV output: `training/output/training_scans.csv`
- App logs: `log/mes_app.log`
