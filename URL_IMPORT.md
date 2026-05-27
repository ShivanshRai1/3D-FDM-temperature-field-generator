# URL Import for Simulation Setup

Opt-in deep links load PCB simulation **input** from URL query parameters, compatible with the heatsimulation PHP style (`3dviewcircuit.php`).

## Behavior

| URL | Result |
|-----|--------|
| No import params | App behaves exactly as before (hardcoded defaults). |
| Import params present | Components and optional globals are loaded from the URL. User clicks **Run Simulation** as usual. |

Restore point before this feature: git tag `backup-pre-url-import-2026-05-26`.

## Gate

Import runs when **any** of these are true:

- `import=1` is present, or
- A known param exists (`W_Q1`, `PLoss_Q1`, `RthCA_Q1`, `fs`, `fsw`, etc.)

## Example URL

```
/pcb_temperature_app.html?import=1&W_Q1=10&L_Q1=15&H_Q1=4.4&PLoss_Q1=20.686&RthCA_Q1=10&RthJC_Q1=0.39&W_D1_D2_D3_D4=15.24&W_D5=10.16&H_D1_D2_D3_D4=6.37&H_D5=4.58&L_D1_D2_D3_D4=15.24&L_D5=15.05&PLoss_D1=4.346&PLoss_D2=4.346&PLoss_D3=4.346&PLoss_D4=4.346&PLoss_D5=15.936&PLoss_inductor=0.33&PLoss_capacitor=0.00021&RthJC_D1_D2_D3_D4=-&RthJC_D5=-&fs=50&fsw=100000
```

## Component parameters

| Component | Width | Length (depth) | Height | Power | Rth keys (first valid wins) |
|-----------|-------|----------------|--------|-------|-----------------------------|
| Q1 | `W_Q1` | `L_Q1` | `H_Q1` | `PLoss_Q1` | `RthCA_Q1`, `RthJC_Q1`, `RthJA_Q1` |
| D1–D4 | `W_D1_D2_D3_D4` | `L_D1_D2_D3_D4` | `H_D1_D2_D3_D4` | `PLoss_D1` … `PLoss_D4` | `RthJC_D1_D2_D3_D4`, `RthJA_D1_D2_D3_D4` |
| D5 | `W_D5` | `L_D5` | `H_D5` | `PLoss_D5` | `RthJC_D5`, `RthJA_D5` |
| Inductor | `W_inductor` (optional) | `L_inductor` | `H_inductor` | `PLoss_inductor` | optional Rth keys |
| Capacitor | `W_capacitor` (optional) | `L_capacitor` | `H_capacitor` | `PLoss_capacitor` | optional Rth keys |

- `W_*` → component length on board (mm), mapped to internal `l`
- `L_*` → component depth (mm), mapped to internal `w`
- `H_*` → height (mm)
- `PLoss_*` → power (W)
- Rth value `-` or missing → component marked `rthMissing`; **Run Simulation** is blocked until Rth is entered in the UI (same as array import)

A component is included only if at least one of its trigger keys appears in the URL.

## Placement

Default fixed layout (mm) is used unless overridden:

| Key | Default x | Default y |
|-----|-----------|-----------|
| Q1 | 10 | 8 |
| D1 | 28 | 8 |
| D2 | 46 | 8 |
| D3 | 28 | 26 |
| D4 | 46 | 26 |
| D5 | 10 | 44 |
| Inductor | 64 | 8 |
| Capacitor | 64 | 24 |

Override: `X_Q1`, `Y_Q1`, `X_D1`, `Y_D1`, etc.

Inductor/capacitor without `W_`/`L_`/`H_` use template default sizes.

## Optional global parameters

| Param | Effect |
|-------|--------|
| `ambient_c` / `ambient` | Ambient temperature (°C) |
| `margin_mm` | Board margin |
| `board_thickness_mm` / `thickness_mm` | PCB thickness |
| `dx`, `dy`, `dz` | Solver grid spacing (mm) |
| `convection_w_m2k` | Convection coefficient |
| `fs`, `fsw` | Stored as metadata only (not used by solver v1) |

Copper layers and vias keep the app defaults unless extended later.

## Missing or invalid parameters

- **No component keys** → import fails; app keeps default setup.
- **Invalid number** (e.g. `PLoss_Q1=abc`) → import fails with an error message.
- **Missing Rth** or `Rth=-` → component loads with warning; run blocked until Rth is set in UI.
- **Missing dimensions** for a triggered component → layout template defaults used.
- **Optional globals missing** → app defaults used.

## Implementation

- Logic: `url_import.js` (isolated, no-op without import params)
- Hook: single call in `pcb_temperature_app.html` after normal init
- Solver/API: unchanged; uses existing `solverConfig()` → `POST /api/simulate/start`

## Not in v1

- Auto-run on load (`?run=1`) — planned as a follow-up
- External JSON config URLs — query-string params only for now
