# Scripting Engine — Practical Guide (Training)

This guide is for non-programmers. It uses one training view and two scripts so you can learn by clicking and watching what changes.

---

## 1) Concept intro (one page)

### What is a script?

A script is a small Python logic file that runs in the app runtime loop. It can:

- react to button events,
- read/write UI state,
- show popup/confirm dialogs,
- process scanner-like input,
- write local CSV output.

### How scripts are triggered

You start scripts from **Settings → Scripts Lab**:

- choose a script,
- click **Start Chain**.

Training scripts:

- `training/training_example_view_1`
- `training/training_example_view_2`

### How scripts read/write state

Scripts use:

- `ctx.set_state(...)` to write values,
- `ctx.values.state(...)` to read values.

The training view shows a live state table so you can see script changes immediately.

### Popup and confirm handling

Scripts use non-blocking popup methods:

- `ctx.ui.popup_message(...)`
- `ctx.ui.popup_confirm(...)`

These return `None` while waiting, then return the result when user clicks.

### TCP scan handling (without real hardware)

Training view has **Simulate incoming scan**.
It publishes a `tcp_client / training_scanner / message` event into WorkerBus.
Scripts read that through `ctx.read_tcp("training_scanner")`.

### CSV writing

Scripts append rows to:

- `training/output/training_scans.csv`

Columns:

- `timestamp`
- `scan_code`
- `counter`

---

## 2) Tutorial — Build your first view script flow

## Step 0: Select training app config

Use set `training`.

- UI path: **Settings → Startup Settings** → choose `training` → save/reload.
- Or run with env: `APP_CONFIG_PATH=config/sets/training.json python main.py`

## Step 1: Open training view

Open route **Training Example**.

You will see:

- control buttons,
- scan simulation section,
- CSV section,
- live state table.

## Step 2: Click buttons and watch state updates

Start script `training/training_example_view_1` in Scripts Lab.
Then click:

- **Action A** / **Action B**
- **Reset state**

Observe in state table:

- `training_last_button`
- `training_status`
- `view_button_states`

## Step 3: Confirm popup controls flow

Click **Ask Confirm**.

- Choose **Yes** or **No**.
- Script writes result into `training_confirm_result`.
- Button enable/disable rules are applied from the confirm result.

## Step 4: Simulate TCP scan and handle in script

Enter a scan code and click **Simulate incoming scan**.

For script 1:

- accepted format: `TRN-*`
- rejected if prefix is different.

On accepted scan, script updates:

- `training_last_scan`
- `training_scan_count`

## Step 5: Write a CSV row

Click **Write CSV row**.

Expected behavior:

- row appended to `training/output/training_scans.csv`
- `training_csv_count` increments
- `training_csv_last_status` shows success/failure

---

## 3) Two scripts for the same view (different system behavior)

Both scripts control the same page: `pages/training/training_example_view.py`.

## `training_example_view_1`

Focus:

- simple training mode
- accepts scans starting with `TRN-`
- basic popup + confirm
- straightforward button enable/disable
- CSV write immediately on button click

## `training_example_view_2`

Focus:

- alternate behavior (“different system”)
- accepts `ALT-` scans (or `TRN-` in relaxed mode)
- mode-sensitive behavior (`strict` / `relaxed`)
- additional confirmation before CSV write
- different button rule strategy

### What changes for users?

- Same screen, different operating rules.
- This is useful for training two line variants without cloning the whole UI.

---

## 4) How to switch between script 1 and script 2

Switching is done in **Scripts Lab**:

1. Stop running training chain (if active).
2. Start `training/training_example_view_1` **or** `training/training_example_view_2`.
3. Go back to **Training Example** view.
4. Confirm active script in state table (`training_active_script`).

> Recommendation: run only one training script instance for this view at a time.

---

## 5) Troubleshooting

## Where logs are

- Runtime/app logs: `log/mes_app.log`
- Script chain logs also appear in Scripts Lab log panel.

## Common mistakes

1. **Wrong event key / stale command**
   - Symptoms: button click does nothing.
   - Check `training_command` and `training_last_button` in state table.

2. **Script not started**
   - Symptoms: view opens but no logic runs.
   - Start one training script in Scripts Lab.

3. **View binding mismatch**
   - Symptoms: button states never update.
   - Check `view_button_states` has keys like `training_example_view.btn_a`.

4. **State key typo**
   - Symptoms: values not updating where expected.
   - Reuse exact key names from training scripts and view.

5. **CSV write fails**
   - Symptoms: error in `training_csv_last_status`.
   - Verify `training/output/` is writable.

## Safe way to modify scripts

- Change one behavior at a time.
- Keep state key names consistent.
- After edits, reload script in Scripts Lab.
- Test with simulated TCP scan before connecting real scanner.
