/**
 * Opt-in URL query-parameter import for Version4 PCB thermal setup.
 * No import params in the URL => this module is a no-op.
 */
(function (global) {
  "use strict";

  const IMPORT_GATE_KEY = "import";
  const TRIGGER_EXACT = new Set(["fs", "fsw"]);
  const TRIGGER_PREFIXES = ["w_", "l_", "h_", "ploss_", "rth", "x_", "y_"];

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

  const COMPONENT_SPECS = [
    {
      layoutKey: "Q1",
      triggerKeys: ["W_Q1", "L_Q1", "H_Q1", "PLoss_Q1", "RthCA_Q1", "RthJC_Q1", "RthJA_Q1"],
      widthKey: "W_Q1",
      lengthKey: "L_Q1",
      heightKey: "H_Q1",
      powerKey: "PLoss_Q1",
      rthJaKeys: ["RthJA_Q1"],
      rthJcKey: "RthJC_Q1",
      rthCaKey: "RthCA_Q1"
    },
    {
      layoutKey: "D1",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D1", "RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D1",
      rthJaKeys: ["RthJA_D1_D2_D3_D4"],
      rthJcKey: "RthJC_D1_D2_D3_D4",
      rthCaKey: "RthCA_D1_D2_D3_D4"
    },
    {
      layoutKey: "D2",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D2"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D2",
      rthJaKeys: ["RthJA_D1_D2_D3_D4"],
      rthJcKey: "RthJC_D1_D2_D3_D4",
      rthCaKey: "RthCA_D1_D2_D3_D4"
    },
    {
      layoutKey: "D3",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D3"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D3",
      rthJaKeys: ["RthJA_D1_D2_D3_D4"],
      rthJcKey: "RthJC_D1_D2_D3_D4",
      rthCaKey: "RthCA_D1_D2_D3_D4"
    },
    {
      layoutKey: "D4",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D4",
      rthJaKeys: ["RthJA_D1_D2_D3_D4"],
      rthJcKey: "RthJC_D1_D2_D3_D4",
      rthCaKey: "RthCA_D1_D2_D3_D4"
    },
    {
      layoutKey: "D5",
      triggerKeys: ["W_D5", "L_D5", "H_D5", "PLoss_D5", "RthJC_D5", "RthJA_D5"],
      widthKey: "W_D5",
      lengthKey: "L_D5",
      heightKey: "H_D5",
      powerKey: "PLoss_D5",
      rthJaKeys: ["RthJA_D5"],
      rthJcKey: "RthJC_D5",
      rthCaKey: "RthCA_D5"
    },
    {
      layoutKey: "inductor",
      triggerKeys: ["PLoss_inductor", "W_inductor", "L_inductor", "H_inductor"],
      widthKey: "W_inductor",
      lengthKey: "L_inductor",
      heightKey: "H_inductor",
      powerKey: "PLoss_inductor",
      rthJaKeys: ["RthJA_inductor"],
      rthJcKey: "RthJC_inductor",
      rthCaKey: "RthCA_inductor"
    },
    {
      layoutKey: "capacitor",
      triggerKeys: ["PLoss_capacitor", "W_capacitor", "L_capacitor", "H_capacitor"],
      widthKey: "W_capacitor",
      lengthKey: "L_capacitor",
      heightKey: "H_capacitor",
      powerKey: "PLoss_capacitor",
      rthJaKeys: ["RthJA_capacitor"],
      rthJcKey: "RthJC_capacitor",
      rthCaKey: "RthCA_capacitor"
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

  function paramKeyMatchesTrigger(key) {
    if (TRIGGER_EXACT.has(key) || TRIGGER_EXACT.has(key.toLowerCase())) {
      return true;
    }
    const lower = key.toLowerCase();
    return TRIGGER_PREFIXES.some(prefix => lower.startsWith(prefix));
  }

  function hasUrlImportParams() {
    const params = readUrlParams();
    if (params[IMPORT_GATE_KEY] === "1") {
      return true;
    }
    if (global.TopologyImport && global.TopologyImport.hasTopologyTitle(params)) {
      return true;
    }
    for (const key of Object.keys(params)) {
      if (paramKeyMatchesTrigger(key)) {
        return true;
      }
    }
    return false;
  }

  function getParam(params, key) {
    if (key === undefined || key === null || String(key).trim() === "") {
      return undefined;
    }
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      return params[key];
    }
    const target = String(key).toLowerCase();
    for (const entryKey of Object.keys(params)) {
      if (entryKey.toLowerCase() === target) {
        return params[entryKey];
      }
    }
    return undefined;
  }

  function hasParam(params, key) {
    return getParam(params, key) !== undefined;
  }

  function isMissingValue(raw) {
    if (raw === undefined || raw === null) return true;
    const text = String(raw).trim();
    return text === "" || text === "-" || /^open$/i.test(text);
  }

  function parseNumber(raw) {
    if (isMissingValue(raw)) {
      return null;
    }
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function parsePower(raw) {
    const value = parseNumber(raw);
    if (value === null || value < 0) return null;
    if (value > 5000) return null;
    return value;
  }

  function specTriggered(spec, params) {
    return spec.triggerKeys.some(key => hasParam(params, key));
  }

  function resolveDimension(params, key, fallback) {
    if (!key) {
      return fallback;
    }
    const parsed = parseNumber(getParam(params, key));
    return parsed !== null ? parsed : fallback;
  }

  function resolvePlacement(params, layoutKey, layout) {
    return {
      x: parseNumber(getParam(params, `X_${layoutKey}`)) ?? layout.x,
      y: parseNumber(getParam(params, `Y_${layoutKey}`)) ?? layout.y
    };
  }

  function missingThermal(mode, primary, secondary, caseTemp) {
    return {
      rthMode: mode,
      rth: Math.max(0.1, primary || 1),
      rthSecondary: secondary ?? null,
      rthCaseToAmbient: mode === "junction_to_case_to_ambient" ? secondary ?? null : null,
      rthCaseTemperatureC: caseTemp ?? null,
      rthMissing: true
    };
  }

  function resolveThermal(params, spec) {
    for (let i = 0; i < (spec.rthJaKeys || []).length; i += 1) {
      const key = spec.rthJaKeys[i];
      if (!hasParam(params, key)) {
        continue;
      }
      const raw = getParam(params, key);
      if (raw === "-" || raw === "") {
        return missingThermal("junction_to_ambient", 1, null, null);
      }
      const value = parseNumber(raw);
      if (value !== null && value > 0) {
        return {
          rthMode: "junction_to_ambient",
          rth: value,
          rthSecondary: null,
          rthCaseToAmbient: null,
          rthCaseTemperatureC: null,
          rthMissing: false
        };
      }
      return missingThermal("junction_to_ambient", 1, null, null);
    }

    const jcPresent = spec.rthJcKey && hasParam(params, spec.rthJcKey);
    const caPresent = spec.rthCaKey && hasParam(params, spec.rthCaKey);
    const jcRaw = jcPresent ? getParam(params, spec.rthJcKey) : undefined;
    const caRaw = caPresent ? getParam(params, spec.rthCaKey) : undefined;
    const jc = jcPresent ? parseNumber(jcRaw) : null;
    const ca = caPresent ? parseNumber(caRaw) : null;
    const jcInvalid = jcPresent && (jcRaw === "-" || jcRaw === "" || jc === null || jc <= 0);
    const caInvalid = caPresent && (caRaw === "-" || caRaw === "" || ca === null || ca <= 0);

    if (jcPresent && caPresent) {
      if (jcInvalid || caInvalid) {
        return missingThermal("junction_to_case_to_ambient", jc || 1, ca || 1, null);
      }
      return {
        rthMode: "junction_to_case_to_ambient",
        rth: jc,
        rthSecondary: ca,
        rthCaseToAmbient: ca,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }

    // Version3 / PHP compat: a lone RthCA or RthJC value is treated as Rth_ja.
    if (caPresent && !caInvalid) {
      return {
        rthMode: "junction_to_ambient",
        rth: ca,
        rthSecondary: null,
        rthCaseToAmbient: null,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }

    if (jcPresent && !jcInvalid) {
      return {
        rthMode: "junction_to_ambient",
        rth: jc,
        rthSecondary: null,
        rthCaseToAmbient: null,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }

    if (caPresent || jcPresent) {
      return missingThermal("junction_to_case_to_ambient", jc || 1, ca || 1, null);
    }

    return missingThermal("junction_to_ambient", 25, null, null);
  }

  function parseUrlImport(params) {
    const globals = {};
    Object.entries(OPTIONAL_GLOBAL_KEYS).forEach(([paramKey, stateKey]) => {
      if (!hasParam(params, paramKey)) {
        return;
      }
      const value = parseNumber(getParam(params, paramKey));
      if (value !== null) {
        globals[stateKey] = value;
      }
    });

    const metadata = {};
    if (hasParam(params, "fs")) {
      metadata.fs = getParam(params, "fs");
    }
    if (hasParam(params, "fsw")) {
      metadata.fsw = getParam(params, "fsw");
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
      const thermal = resolveThermal(params, spec);
      components.push({
        id: layout.id,
        name: layout.name,
        x: placement.x,
        y: placement.y,
        l: Math.max(0.5, resolveDimension(params, spec.widthKey, layout.l)),
        w: Math.max(0.5, resolveDimension(params, spec.lengthKey, layout.w)),
        h: Math.max(0.1, resolveDimension(params, spec.heightKey, layout.h)),
        power: Math.max(0, parsePower(getParam(params, spec.powerKey)) ?? 0),
        rotation: 0,
        urlImportKey: spec.layoutKey,
        ...thermal
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
        warnings.push(
          `${component.name}: thermal resistance is missing or invalid in the URL. Complete the selected Rth path in the UI before running.`
        );
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
        if (!key || !hasParam(parsed.params, key)) {
          return;
        }
        const raw = getParam(parsed.params, key);
        if (isMissingValue(raw)) {
          return;
        }
        if (parseNumber(raw) === null) {
          errors.push(`${name}: invalid numeric value for ${key}.`);
        }
      });
      if (spec.powerKey && hasParam(parsed.params, spec.powerKey)) {
        const raw = getParam(parsed.params, spec.powerKey);
        if (!isMissingValue(raw) && parsePower(raw) === null) {
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

  async function loadIntoState(state) {
    if (!hasUrlImportParams()) {
      return { ok: false, skipped: true };
    }
    const params = readUrlParams();
    let parsed;
    let validation;
    if (global.TopologyImport && global.TopologyImport.hasTopologyTitle(params)) {
      try {
        parsed = await global.TopologyImport.parseTopologyImport(params, state.marginMm);
        validation = global.TopologyImport.validateTopologyImport(parsed);
      } catch (error) {
        return {
          ok: false,
          skipped: false,
          errors: [error.message],
          warnings: []
        };
      }
    } else {
      parsed = parseUrlImport(params);
      validation = validateUrlImport(parsed);
    }
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
