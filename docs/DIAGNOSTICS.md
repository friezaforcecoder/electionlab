# ElectionLab diagnostics — 0.10

ElectionLab writes one recurrent diagnostic file per launch:

`<data root>/Logs/latest_session.log`

The file is truncated at startup so it always represents the current/most recent session. It intentionally does not log API-key values.

## What is recorded
- build / Python / operating-system metadata,
- non-secret provider/settings readiness,
- startup and Knowledge Vault seed duration,
- navigation page and duration,
- Campaign HQ refresh duration,
- results-map and campaign-map selected state + detail-render duration,
- simulation request / completion / failure,
- campaign advancement, state operations and polling snapshots,
- uncaught exceptions,
- UI heartbeat gaps above the stall threshold.

## UI stall watchdog
A Qt timer is expected to fire every 250 ms. If the GUI thread is blocked, the timer fires late after the application recovers. ElectionLab records that gap as `UI_STALL_DETECTED` along with the current action marker. This does not prevent a stall; it makes the next stall diagnosable.

## User workflow
If a freeze happens:
1. Allow ElectionLab to recover if possible.
2. Open Settings → Diagnostics.
3. Click **Open Latest Session Log** or **Copy Log Path**.
4. Share `latest_session.log` together with what you clicked immediately before the stall.
