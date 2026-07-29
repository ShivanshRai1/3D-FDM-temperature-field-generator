/**
 * V2 copy — DiscoverEE URL import for pcb_temperature_app_v2.html.
 * Keep V1 (url_import.js) unchanged. New *_PL / pl= format goes here.
 */
(function (global) {
  "use strict";

  const IMPORT_GATE_KEY = "import";
  const DEFAULT_RTH_CA = 1;
  const DEFAULT_AMBIENT_C = 25;
  const TRIGGER_EXACT = new Set(["fs", "fsw", "pl", "t_ambient"]);
  const TRIGGER_PREFIXES = ["w_", "l_", "h_", "ploss_", "rth", "x_", "y_"];
  const TRIGGER_SUFFIXES = ["_pl"];

  const OPTIONAL_GLOBAL_KEYS = {
    t_ambient: "ambientC",
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
      rthJcKeys: ["RthJC_Q1"],
      rthCaKeys: ["RthCA_Q1"]
    },
    {
      layoutKey: "D1",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D1", "RthJC_D1", "RthJA_D1", "RthJC_D1_D2_D3_D4", "RthJA_D1_D2_D3_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D1",
      rthJaKeys: ["RthJA_D1", "RthJA_D1_D2_D3_D4"],
      rthJcKeys: ["RthJC_D1", "RthJC_D1_D2_D3_D4"],
      rthCaKeys: ["RthCA_D1", "RthCA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D2",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D2", "RthJC_D2", "RthJA_D2"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D2",
      rthJaKeys: ["RthJA_D2", "RthJA_D1_D2_D3_D4"],
      rthJcKeys: ["RthJC_D2", "RthJC_D1_D2_D3_D4"],
      rthCaKeys: ["RthCA_D2", "RthCA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D3",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D3", "RthJC_D3", "RthJA_D3"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D3",
      rthJaKeys: ["RthJA_D3", "RthJA_D1_D2_D3_D4"],
      rthJcKeys: ["RthJC_D3", "RthJC_D1_D2_D3_D4"],
      rthCaKeys: ["RthCA_D3", "RthCA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D4",
      triggerKeys: ["W_D1_D2_D3_D4", "L_D1_D2_D3_D4", "H_D1_D2_D3_D4", "PLoss_D4", "RthJC_D4", "RthJA_D4"],
      widthKey: "W_D1_D2_D3_D4",
      lengthKey: "L_D1_D2_D3_D4",
      heightKey: "H_D1_D2_D3_D4",
      powerKey: "PLoss_D4",
      rthJaKeys: ["RthJA_D4", "RthJA_D1_D2_D3_D4"],
      rthJcKeys: ["RthJC_D4", "RthJC_D1_D2_D3_D4"],
      rthCaKeys: ["RthCA_D4", "RthCA_D1_D2_D3_D4"]
    },
    {
      layoutKey: "D5",
      triggerKeys: ["W_D5", "L_D5", "H_D5", "PLoss_D5", "RthJC_D5", "RthJA_D5"],
      widthKey: "W_D5",
      lengthKey: "L_D5",
      heightKey: "H_D5",
      powerKey: "PLoss_D5",
      rthJaKeys: ["RthJA_D5"],
      rthJcKeys: ["RthJC_D5"],
      rthCaKeys: ["RthCA_D5"]
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

  function repairSearchString(search) {
    if (!search || search.length < 2) {
      return search;
    }
    let repaired = search;
    // Common DiscoverEE typo: missing & after email domain before topology_title.
    repaired = repaired.replace(/(\.(?:in|com|io|net|org))topology_title=/gi, "$1&topology_title=");
    const gluedParams = ["topology_title", "username", "import"];
    for (let i = 0; i < gluedParams.length; i += 1) {
      const name = gluedParams[i];
      const re = new RegExp(`([^&?])(${name}=)`, "gi");
      repaired = repaired.replace(re, "$1&$2");
    }
    return repaired;
  }

  function normalizeParsedParams(out) {
    const username = out.username;
    if (username && /topology_title=/i.test(username)) {
      const splitMatch = String(username).match(/^([\s\S]*?)[.&]?topology_title=(.*)$/i);
      if (splitMatch) {
        const cleanUser = splitMatch[1].replace(/[.&]+$/, "").trim();
        if (cleanUser) {
          out.username = cleanUser;
        }
        if (!out.topology_title && splitMatch[2]) {
          out.topology_title = splitMatch[2].split("&")[0];
        }
      }
    }
    return out;
  }

  function readUrlParams() {
    const search = repairSearchString(global.location.search);
    const params = new URLSearchParams(search);
    const out = {};
    params.forEach((value, key) => {
      out[key] = value;
    });
    return normalizeParsedParams(out);
  }

  function paramKeyMatchesTrigger(key) {
    if (TRIGGER_EXACT.has(key) || TRIGGER_EXACT.has(key.toLowerCase())) {
      return true;
    }
    const lower = key.toLowerCase();
    if (TRIGGER_PREFIXES.some(prefix => lower.startsWith(prefix))) {
      return true;
    }
    return TRIGGER_SUFFIXES.some(suffix => lower.endsWith(suffix));
  }

  function hasUrlImportParams() {
    const params = readUrlParams();
    if (params[IMPORT_GATE_KEY] === "1") {
      return true;
    }
    if (global.TopologyImport && typeof global.TopologyImport.shouldHandleImport === "function") {
      if (global.TopologyImport.shouldHandleImport(params)) {
        return true;
      }
    } else if (global.TopologyImport && global.TopologyImport.hasTopologyTitle(params)) {
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

  function firstParamRaw(params, keys) {
    if (!keys || !keys.length) {
      return { key: null, raw: undefined };
    }
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (!hasParam(params, key)) {
        continue;
      }
      return { key, raw: getParam(params, key) };
    }
    return { key: null, raw: undefined };
  }

  function getGlobalRthCa(params) {
    for (const key of Object.keys(params)) {
      if (/^rth_?ca(\[\])?$/i.test(key) || key.toLowerCase() === "rthca") {
        if (isMissingValue(params[key])) {
          return DEFAULT_RTH_CA;
        }
        const value = parseNumber(params[key]);
        if (value !== null && value > 0) return value;
        return DEFAULT_RTH_CA;
      }
    }
    const legacy = parseNumber(getParam(params, "RthCA"));
    if (legacy !== null && legacy > 0) return legacy;
    return DEFAULT_RTH_CA;
  }

  function defaultThermal(mode, primary, secondary, caseTemp) {
    const rth = Math.max(0.1, primary || DEFAULT_RTH_CA);
    const useSecondary = mode === "junction_to_case_to_ambient";
    const rthSecondary = useSecondary ? Math.max(0.1, secondary ?? DEFAULT_RTH_CA) : null;
    return {
      rthMode: mode,
      rth,
      rthSecondary,
      rthCaseToAmbient: useSecondary ? rthSecondary : null,
      rthCaseTemperatureC: caseTemp ?? null,
      rthMissing: false
    };
  }

  function resolveThermal(params, spec) {
    const globalCa = getGlobalRthCa(params);

    for (let i = 0; i < (spec.rthJaKeys || []).length; i += 1) {
      const key = spec.rthJaKeys[i];
      if (!hasParam(params, key)) {
        continue;
      }
      const raw = getParam(params, key);
      if (isMissingValue(raw)) {
        continue;
      }
      const value = parseNumber(raw);
      if (value !== null && value > 0) {
        return defaultThermal("junction_to_ambient", value, null, null);
      }
    }

    const jcKeys = spec.rthJcKeys || (spec.rthJcKey ? [spec.rthJcKey] : []);
    const caKeys = spec.rthCaKeys || (spec.rthCaKey ? [spec.rthCaKey] : []);
    const jcEntry = firstParamRaw(params, jcKeys);
    const caEntry = firstParamRaw(params, caKeys);
    const jcPresent = jcEntry.key !== null && !isMissingValue(jcEntry.raw);
    const caPresent = caEntry.key !== null && !isMissingValue(caEntry.raw);
    const jc = jcPresent ? parseNumber(jcEntry.raw) : null;
    const ca = caPresent ? parseNumber(caEntry.raw) : null;

    if (jc !== null && jc > 0 && ca !== null && ca > 0) {
      return defaultThermal("junction_to_case_to_ambient", jc, ca, null);
    }
    if (ca !== null && ca > 0) {
      return defaultThermal("junction_to_ambient", ca, null, null);
    }
    if (jc !== null && jc > 0) {
      return defaultThermal("junction_to_ambient", jc, null, null);
    }

    return defaultThermal("junction_to_ambient", globalCa, null, null);
  }

  function collectImportGlobals(params) {
    const globals = { importDefaults: [] };
    Object.entries(OPTIONAL_GLOBAL_KEYS).forEach(([paramKey, stateKey]) => {
      if (!hasParam(params, paramKey)) {
        return;
      }
      const raw = getParam(params, paramKey);
      if (isMissingValue(raw)) {
        if (stateKey === "ambientC") {
          globals.ambientC = DEFAULT_AMBIENT_C;
          globals.importDefaults.push("T_AMBIENT");
        }
        return;
      }
      const value = parseNumber(raw);
      if (value !== null) {
        globals[stateKey] = value;
      } else if (stateKey === "ambientC") {
        globals.ambientC = DEFAULT_AMBIENT_C;
        globals.importDefaults.push("T_AMBIENT");
      }
    });
    return globals;
  }

  function parseUrlImport(params) {
    const globals = collectImportGlobals(params);

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
    const info = [];

    if (!parsed.components.length) {
      errors.push(
        "No recognizable component parameters were found in the URL. " +
        "Expected keys such as W_Q1, PLoss_Q1, PLoss_D1, or import=1 with component params."
      );
      return { ok: false, errors, warnings, info };
    }

    parsed.components.forEach(component => {
      if (component.rthMissing) {
        warnings.push(
          `${component.name}: Rth is missing or empty in the URL. Enter Rth in the form before Run Simulation.`
        );
      }
    });

    if (parsed.globals && Array.isArray(parsed.globals.importDefaults)) {
      if (parsed.globals.importDefaults.includes("T_AMBIENT")) {
        info.push("T_AMBIENT was empty — using 25°C.");
      }
    }
    const hasGlobalRthKey = Object.keys(parsed.params || {}).some(key => /^rth_?ca(\[\])?$/i.test(key) || key.toLowerCase() === "rthca");
    const globalRthRaw = hasGlobalRthKey
      ? Object.entries(parsed.params).find(([key]) => /^rth_?ca(\[\])?$/i.test(key) || key.toLowerCase() === "rthca")?.[1]
      : undefined;
    if (!hasGlobalRthKey) {
      info.push("No Rth in URL — using default 1.");
    } else if (isMissingValue(globalRthRaw)) {
      info.push("Rth_ca[] was empty — using default 1.");
    }

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

    return { ok: errors.length === 0, errors, warnings, info };
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
    const useTopologyImport = global.TopologyImport && (
      (typeof global.TopologyImport.shouldHandleImport === "function" && global.TopologyImport.shouldHandleImport(params)) ||
      global.TopologyImport.hasTopologyTitle(params)
    );
    if (useTopologyImport) {
      try {
        parsed = await global.TopologyImport.parseTopologyImport(params, state.marginMm);
        validation = global.TopologyImport.validateTopologyImport(parsed);
      } catch (error) {
        return {
          ok: false,
          skipped: false,
          errors: [error.message],
          warnings: [],
          info: []
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
      info: validation.info || [],
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
