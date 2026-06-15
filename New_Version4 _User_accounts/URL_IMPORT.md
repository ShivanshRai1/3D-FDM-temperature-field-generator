# URL Import for Simulation Setup (Version4)

Opt-in deep links load PCB simulation **input** from URL query parameters, compatible with the heatsimulation PHP style (`3dviewcircuit.php`).

## Behavior

| URL | Result |
|-----|--------|
| No import params | App behaves exactly as before (default components, accounts, saved runs). |
| Import params present | Components and optional globals load from the URL. User clicks **Run Simulation** as usual. |

## Gate

Import runs when **any** of these are true:

- `import=1` is present, or
- A known param exists (`W_Q1`, `PLoss_Q1`, `RthCA_Q1`, `fs`, `fsw`, etc.)

Param names are matched **case-insensitively** (`PLoss_Q1` and `Ploss_Q1` both work).

## Example URL

```
/pcb_temperature_app.html?import=1&W_Q1=10&L_Q1=15&H_Q1=4.4&PLoss_Q1=20.686&RthCA_Q1=10&RthJC_Q1=0.39
```

## Version4 thermal resistance mapping

| URL keys | Version4 mode |
|----------|----------------|
| `RthJA_*` | `junction_to_ambient` (Rth_ja) |
| `RthJC_*` + `RthCA_*` (both present and valid) | `junction_to_case_to_ambient` (Rth_jc + Rth_ca) |
| `RthCA_*` or `RthJC_*` alone | `junction_to_ambient` (Version3 / PHP compat — first valid key wins) |
| `-` or invalid | `rthMissing` — complete values in UI before running |

See `README.md` for all six supported Rth paths in manual entry.

## Component parameters

Same schema as Version3 — see component table in project root `URL_IMPORT.md` or heatsimulation PHP URLs.

- `W_*` → internal `l` (mm)
- `L_*` → internal `w` (mm)
- `H_*` → height (mm)
- `PLoss_*` → power (W)

## Implementation

- Logic: `url_import.js` (isolated, no-op without import params)
- Hook: single call in `pcb_temperature_app.html` after normal init
- Solver/API/accounts: unchanged

## Not in v1

- Auto-run on load (`?run=1`)
- Live database / model selector API (separate future work)
