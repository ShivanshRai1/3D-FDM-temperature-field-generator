/**
 * Opt-in URL query-parameter import for PCB thermal simulation setup.
 * No import params in the URL => this module is a no-op.
 */
(function (global) {
  "use strict";

  const IMPORT_GATE_KEY = "import";
  const TRIGGER_EXACT = new Set(["fs", "fsw"]);
  const TRIGGER_PREFIXES = ["W_", "L_", "H_", "PLoss_", "Rth"];

  const OPTIONAL_GLOBAL_KEYS = {
    ambient_c: "ambientC",
    ambient: "ambientC",
    margin_mm: "marginMm",
    board_thickness_mm: "pcbThicknessMm",
    thickness_mm: "pcbThicknessMm",
    dx: "dx",
    dy: "dy",
    dz: "dz",
    convection_w_m2k: "convectionCoefficientWm2K"
  };

  /**
   * Fixed board positions (mm) for the buck-converter URL schema.
   * Override with X_<key> and Y_<key> URL params when provided.
   */
  const LAYOUT = {
    Q1: { id: "Q1", name: "Q1", x: 10, y: 8, l: 10, w: 15, h: 4.4 },
    D1: { id: "D1", name: "D1", x: 28, y: 8, l: 15.24, w: 15.24, h: 6.37 },
    D2: { id: "D2", name: "D2", x: 46, y: 8, l: 15.24, w: 15.24, h: 6.37 },
    D3: { id: "D3", name: "D3", x: 28, y: 26, l: 15.24, w: 15.24, h: 6.37 },
    D4: { id: "D4", name: "D4", x: 46, y: 26, l: 15.24, w: 15.24, h: 6.37 },
    D5: { id: "D5", name: "D5", x: 10, y: 44, l: 15.05, w: 10.16, h: 4.58 },
    inductor: { id: "L1", name: "Inductor", x: 64, y: 8, l: 8, w: 8, h: 4 },
    capacitor: { id: "C1", name: "Capacitor", x: 64, y: 24, l: 4, w: 4, h: 2 }
  };

  /** Component definitions aligned with heatsimulation/3dviewcircuit.php style URLs. */
  const COMPONENT_SPECS = [
    {
      layoutKey: "Q1",
      triggerKeys: ["W_Q1", "L_Q1", "H_Q1", "PLoss_Q1", "RthCA_Q1", "RthJC_Q1"],
      widthKey: "W_Q1",
      lengthKey: "L_Q1",
      heightKey: "H_Q1",
      powerKey: "PLoss_Q1",
      rthKeys: ["RthCA_Q1", "RthJC_Q1", "RthJA_Q1"]
    },
    {
      layoutKey: "D1",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D1", "RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D1",
      rthKeys: ["RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D2",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D2"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D2",
      rthKeys: ["RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D3",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D3"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D3",
      rthKeys: ["RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D4",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D4",
      rthKeys: ["RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D5",
      triggerKeys: ["W_D5", "L_D5", "H_D5", "PLoss_D5", "RthJC_D5", "RthJA_D5"],
      widthKey: "W_D5",
      lengthKey: "L_D5",
      heightKey: "H_D5",
      powerKey: "PLoss_D5",
      rthKeys: ["RthJC_D5", "RthJA_D5"]
    },
    {
      layoutKey: "inductor",
      triggerKeys: ["PLoss_inductor", "W_inductor", "L_inductor", "H_inductor"],
      widthKey: "W_inductor",
      lengthKey: "L_inductor",
      heightKey: "H_inductor",
      powerKey: "PLoss_inductor",
      rthKeys: ["RthCA_inductor", "RthJC_inductor", "RthJA_inductor"]
    },
    {
      layoutKey: "capacitor",
      triggerKeys: ["PLoss_capacitor", "W_capacitor", "L_capacitor", "H_capacitor"],
      widthKey: "W_capacitor",
      lengthKey: "L_capacitor",
      heightKey: "H_capacitor",
      powerKey: "PLoss_capacitor",
      rthKeys: ["RthCA_capacitor", "RthJC_capacitor", "RthJA_capacitor"]
    }
  ];

  function readUrlParams() {
    const params = new URLSearchParams(global.location.search);
    const out = {};
    params.forEach((value, key) => {
      out[key] = value;
    });
    return out;
  }

  function hasUrlImportParams() {
    const params = new URLSearchParams(global.location.search);
    if (params.get(IMPORT_GATE_KEY) === "1") {
      return true;
    }
    for (const [key] of params.entries()) {
      if (TRIGGER_EXACT.has(key)) {
        return true;
      }
      if (TRIGGER_PREFIXES.some(prefix => key.startsWith(prefix))) {
        return true;
      }
    }
    return false;
  }

  function parseNumber(raw) {
    if (raw === undefined || raw === null || raw === "") {
      return null;
    }
    if (String(raw).trim() === "-") {
      return null;
    }
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function specTriggered(spec, params) {
    return spec.triggerKeys.some(key => Object.prototype.hasOwnProperty.call(params, key));
  }

  function resolveDimension(params, key, fallback) {
    const parsed = parseNumber(params[key]);
    if (parsed !== null) {
      return parsed;
    }
    return fallback;
  }

  function resolvePlacement(params, layoutKey, layout) {
    const xKey = `X_${layoutKey}`;
    const yKey = `Y_${layoutKey}`;
    return {
      x: parseNumber(params[xKey]) ?? layout.x,
      y: parseNumber(params[yKey]) ?? layout.y
    };
  }

  function resolveRth(params, rthKeys) {
    for (let i = 0; i < rthKeys.length; i += 1) {
      const key = rthKeys[i];
      if (!Object.prototype.hasOwnProperty.call(params, key)) {
        continue;
      }
      const raw = params[key];
      if (raw === "-" || raw === "") {
        return { rth: 1, rthMissing: true, sourceKey: key };
      }
      const value = parseNumber(raw);
      if (value !== null && value > 0) {
        return { rth: value, rthMissing: false, sourceKey: key };
      }
      if (Object.prototype.hasOwnProperty.call(params, key)) {
        return { rth: 1, rthMissing: true, sourceKey: key };
      }
    }
    return { rth: 1, rthMissing: true, sourceKey: null };
  }

  function parseUrlImport(params) {
    const globals = {};
    Object.entries(OPTIONAL_GLOBAL_KEYS).forEach(([paramKey, stateKey]) => {
      if (!Object.prototype.hasOwnProperty.call(params, paramKey)) {
        return;
      }
      const value = parseNumber(params[paramKey]);
      if (value !== null) {
        globals[stateKey] = value;
      }
    });

    const metadata = {};
    if (Object.prototype.hasOwnProperty.call(params, "fs")) {
      metadata.fs = params.fs;
    }
    if (Object.prototype.hasOwnProperty.call(params, "fsw")) {
      metadata.fsw = params.fsw;
    }

    const components = [];
    COMPONENT_SPECS.forEach(spec => {
      if (!specTriggered(spec, params)) {
        return;
      }
      const layout = LAYOUT[spec.layoutKey];
      if (!layout) {
        return;
      }
      const placement = resolvePlacement(params, spec.layoutKey, layout);
      const l = resolveDimension(params, spec.widthKey, layout.l);
      const w = resolveDimension(params, spec.lengthKey, layout.w);
      const h = resolveDimension(params, spec.heightKey, layout.h);
      const power = parseNumber(params[spec.powerKey]) ?? 0;
      const rthInfo = resolveRth(params, spec.rthKeys || []);

      components.push({
        id: layout.id,
        name: layout.name,
        x: placement.x,
        y: placement.y,
        l: Math.max(0.5, l),
        w: Math.max(0.5, w),
        h: Math.max(0.1, h),
        power: Math.max(0, power),
        rth: Math.max(0.1, rthInfo.rth),
        rthMissing: rthInfo.rthMissing,
        rotation: 0,
        urlImportKey: spec.layoutKey
      });
    });

    return { globals, metadata, components, params };
  }

  function validateUrlImport(parsed) {
    const errors = [];
    const warnings = [];

    if (!parsed.components.length) {
      errors.push(
        "No recognizable component parameters were found in the URL. " +
        "Expected keys such as W_Q1, PLoss_Q1, PLoss_D1, or import=1 with component params."
      );
      return { ok: false, errors, warnings };
    }

    parsed.components.forEach(component => {
      if (component.rthMissing) {
        warnings.push(`${component.name}: thermal resistance (Rth) is missing or invalid in the URL. Enter Rth in the UI before running.`);
      }
      if (component.power <= 0) {
        warnings.push(`${component.name}: power loss is zero or missing (PLoss_*).`);
      }
    });

    COMPONENT_SPECS.forEach(spec => {
      if (!specTriggered(spec, parsed.params)) {
        return;
      }
      const layout = LAYOUT[spec.layoutKey];
      const name = layout ? layout.name : spec.layoutKey;
      ["widthKey", "lengthKey", "heightKey"].forEach(field => {
        const key = spec[field];
        if (!key || !Object.prototype.hasOwnProperty.call(parsed.params, key)) {
          return;
        }
        const value = parseNumber(parsed.params[key]);
        if (value === null) {
          errors.push(`${name}: invalid numeric value for ${key}.`);
        }
      });
      if (spec.powerKey && Object.prototype.hasOwnProperty.call(parsed.params, spec.powerKey)) {
        const power = parseNumber(parsed.params[spec.powerKey]);
        if (power === null) {
          errors.push(`${name}: invalid numeric value for ${spec.powerKey}.`);
        }
      }
    });

    if (parsed.globals.ambientC !== undefined && (parsed.globals.ambientC < -273 || parsed.globals.ambientC > 200)) {
      warnings.push("ambient_c looks unusual; verify the ambient temperature value.");
    }

    return { ok: errors.length === 0, errors, warnings };
  }

  function applyUrlImport(state, parsed) {
    state.components = parsed.components.map(component => ({
      ...component,
      z: state.pcbThicknessMm
    }));
    state.result = null;
    state.resultPage = false;
    state.lastRunLog = null;
    state.activeResultLayerId = null;
    state.selected = parsed.components.length ? parsed.components[0].id : null;
    state.urlImportActive = true;
    state.urlImportMeta = parsed.metadata;

    if (parsed.globals.marginMm !== undefined) {
      state.marginMm = Math.max(0, parsed.globals.marginMm);
    }
    if (parsed.globals.pcbThicknessMm !== undefined) {
      state.pcbThicknessMm = Math.max(0.2, parsed.globals.pcbThicknessMm);
      state.components.forEach(component => {
        component.z = state.pcbThicknessMm;
      });
      state.layers.forEach(layer => {
        layer.z = Math.min(state.pcbThicknessMm, Math.max(0, layer.z));
      });
    }
    if (parsed.globals.ambientC !== undefined) {
      state.ambientTemperatureC = parsed.globals.ambientC;
    }
    if (parsed.globals.convectionCoefficientWm2K !== undefined) {
      state.convectionCoefficientWm2K = Math.max(0, parsed.globals.convectionCoefficientWm2K);
    }
    state.urlImportGrid = {
      dx: parsed.globals.dx,
      dy: parsed.globals.dy,
      dz: parsed.globals.dz
    };
  }

  function writeInputValue(id, value) {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null && Number.isFinite(value)) {
      el.value = String(value);
    }
  }

  function syncDomFromState(state) {
    writeInputValue("thicknessInput", state.pcbThicknessMm);
    writeInputValue("ambientInput", state.ambientTemperatureC);
    writeInputValue("convectionInput", state.convectionCoefficientWm2K);
    if (state.urlImportGrid) {
      writeInputValue("dxInput", state.urlImportGrid.dx);
      writeInputValue("dyInput", state.urlImportGrid.dy);
      writeInputValue("dzInput", state.urlImportGrid.dz);
    }
  }

  function loadIntoState(state) {
    if (!hasUrlImportParams()) {
      return { ok: false, skipped: true };
    }
    const params = readUrlParams();
    const parsed = parseUrlImport(params);
    const validation = validateUrlImport(parsed);
    if (!validation.ok) {
      return {
        ok: false,
        skipped: false,
        errors: validation.errors,
        warnings: validation.warnings
      };
    }
    applyUrlImport(state, parsed);
    return {
      ok: true,
      skipped: false,
      errors: [],
      warnings: validation.warnings,
      componentCount: parsed.components.length,
      metadata: parsed.metadata
    };
  }

  global.UrlImport = {
    hasUrlImportParams,
    readUrlParams,
    parseUrlImport,
    validateUrlImport,
    applyUrlImport,
    syncDomFromState,
    loadIntoState
  };
})(window);
