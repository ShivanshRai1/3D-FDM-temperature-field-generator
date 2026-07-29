/**
 * DiscoverEE topology_title import: component X/Y from topology layouts,
 * dimensions and power from URL parameters.
 */
(function (global) {
  "use strict";

  const MAX_REASONABLE_POWER_W = 5000;
  const DEFAULT_RTH_CA = 1;
  const DEFAULT_AMBIENT_C = 25;
  const DISPLAY_NAMES = {
    Cin: "Input capacitor",
    Cout: "Output capacitor",
    Lin: "Inductor",
    Lout: "Output inductor"
  };

  let layoutsCache = null;

  function normalizeTopologyTitle(title) {
    return String(title || "").trim().replace(/_/g, " ").replace(/\s+/g, " ");
  }

  function getParam(params, key) {
    if (!key) return undefined;
    if (Object.prototype.hasOwnProperty.call(params, key)) return params[key];
    const target = String(key).toLowerCase();
    for (const entryKey of Object.keys(params)) {
      if (entryKey.toLowerCase() === target) return params[entryKey];
    }
    return undefined;
  }

  function isMissingValue(raw) {
    if (raw === undefined || raw === null) return true;
    const text = String(raw).trim();
    return text === "" || text === "-" || /^open$/i.test(text);
  }

  function parseOptionalNumber(raw) {
    if (isMissingValue(raw)) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function parseOptionalPower(raw) {
    const value = parseOptionalNumber(raw);
    if (value === null || value < 0) return null;
    if (value > MAX_REASONABLE_POWER_W) return null;
    return value;
  }

  function firstPower(params, keys) {
    for (let i = 0; i < keys.length; i += 1) {
      const raw = getParam(params, keys[i]);
      if (isMissingValue(raw)) continue;
      const value = parseOptionalPower(raw);
      if (value !== null) return value;
    }
    return 0;
  }

  function powerKeysForLabel(label) {
    if (label === "Q1") return ["PLoss_Q1", "PLoss_FET_Total[W]_key"];
    if (label === "Q2") return ["PLoss_Q2"];
    if (/^D\d+$/.test(label)) return [`PLoss_${label}`];
    if (label === "Lin") return ["PLoss_inductor", "PLin[W]_key"];
    if (label === "Cin") return ["PLoss_capacitor_cin", "PCin[W]_key"];
    if (label === "Cout") return ["PLoss_capacitor", "PCout[W]_key"];
    if (label === "Lout") return ["PLoss_Lout", "PLout[W]_key"];
    return [`PLoss_${label}`];
  }

  function dimensionKeysForLabel(label) {
    if (label === "Lin") return { w: "W_inductor", l: "L_inductor", h: "H_inductor" };
    if (label === "Cin") return { w: "W_capacitor_cin", l: "L_capacitor_cin", h: "H_capacitor_cin" };
    if (label === "Cout") return { w: "W_capacitor", l: "L_capacitor", h: "H_capacitor" };
    if (label === "Lout") return { w: "W_Lout", l: "L_Lout", h: "H_Lout" };
    if (/^Q\d+$/.test(label)) return { w: `W_${label}`, l: `L_${label}`, h: `H_${label}` };
    if (/^D\d+$/.test(label)) {
      return { w: "W_D1_D2_D3_D4", l: "L_D1_D2_D3_D4", h: "H_D1_D2_D3_D4" };
    }
    return { w: `W_${label}`, l: `L_${label}`, h: `H_${label}` };
  }

  function rthKeyCandidates(label, suffix) {
    if (/^[QD]\d+$/.test(label)) {
      const keys = [`Rth${suffix}_${label}`];
      if (/^D\d+$/.test(label)) {
        keys.push(`Rth${suffix}_D1_D2_D3_D4`);
      }
      return keys;
    }
    return [];
  }

  function firstParamRaw(params, keys) {
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      const raw = getParam(params, key);
      if (raw !== undefined) {
        return { key, raw };
      }
    }
    return { key: null, raw: undefined };
  }

  function rthKeysForLabel(label) {
    if (/^[QD]\d+$/.test(label)) {
      return {
        ja: rthKeyCandidates(label, "JA"),
        jc: rthKeyCandidates(label, "JC"),
        ca: rthKeyCandidates(label, "CA")
      };
    }
    return { ja: [], jc: [], ca: [] };
  }

  function getGlobalRthCa(params) {
    for (const key of Object.keys(params)) {
      if (/^rth_?ca(\[\])?$/i.test(key) || key.toLowerCase() === "rthca") {
        if (isMissingValue(params[key])) {
          return DEFAULT_RTH_CA;
        }
        const value = parseOptionalNumber(params[key]);
        if (value !== null && value > 0) return value;
        return DEFAULT_RTH_CA;
      }
    }
    const legacy = parseOptionalNumber(getParam(params, "RthCA"));
    if (legacy !== null && legacy > 0) return legacy;
    return DEFAULT_RTH_CA;
  }

  function defaultThermal(mode, primary, secondary) {
    const rth = Math.max(0.1, primary || DEFAULT_RTH_CA);
    const useSecondary = mode === "junction_to_case_to_ambient";
    const rthSecondary = useSecondary ? Math.max(0.1, secondary ?? DEFAULT_RTH_CA) : null;
    return {
      rthMode: mode,
      rth,
      rthSecondary,
      rthCaseToAmbient: useSecondary ? rthSecondary : null,
      rthCaseTemperatureC: null,
      rthMissing: false
    };
  }

  function resolveThermal(params, label) {
    const keys = rthKeysForLabel(label);
    const globalCa = getGlobalRthCa(params);
    const jaEntry = firstParamRaw(params, keys.ja);

    if (jaEntry.key && !isMissingValue(jaEntry.raw)) {
      const value = parseOptionalNumber(jaEntry.raw);
      if (value !== null && value > 0) {
        return defaultThermal("junction_to_ambient", value);
      }
    }

    const jcEntry = firstParamRaw(params, keys.jc);
    const caEntry = firstParamRaw(params, keys.ca);
    const jcPresent = jcEntry.key !== null && !isMissingValue(jcEntry.raw);
    const caPresent = caEntry.key !== null && !isMissingValue(caEntry.raw);
    const jc = jcPresent ? parseOptionalNumber(jcEntry.raw) : null;
    const ca = caPresent ? parseOptionalNumber(caEntry.raw) : null;

    if (jc !== null && jc > 0 && ca !== null && ca > 0) {
      return defaultThermal("junction_to_case_to_ambient", jc, ca);
    }
    if (ca !== null && ca > 0) {
      return defaultThermal("junction_to_ambient", ca);
    }
    if (jc !== null && jc > 0) {
      return defaultThermal("junction_to_ambient", jc);
    }

    return defaultThermal("junction_to_ambient", globalCa);
  }

  function resolveDimension(params, key, fallback) {
    if (!key) return fallback;
    const value = parseOptionalNumber(getParam(params, key));
    return value !== null && value > 0 ? value : fallback;
  }

  function componentId(label, index) {
    const clean = String(label || "component").replace(/[^\w]+/g, "_");
    return `${clean}_${index}`;
  }

  function displayName(label) {
    return DISPLAY_NAMES[label] || label;
  }

  function topologyToBoardComponents(layoutComponents, params, marginMm) {
    const boardPoints = layoutComponents.map(item => ({ x: item.x, y: -item.z }));
    const minX = Math.min(...boardPoints.map(point => point.x));
    const minY = Math.min(...boardPoints.map(point => point.y));
    const margin = Math.max(0, marginMm || 8);

    return layoutComponents.map((item, index) => {
      const dims = dimensionKeysForLabel(item.label);
      const thermal = resolveThermal(params, item.label);
      const point = boardPoints[index];
      return {
        id: componentId(item.label, index),
        name: displayName(item.label),
        label: item.label,
        x: point.x - minX + margin,
        y: point.y - minY + margin,
        l: Math.max(0.5, resolveDimension(params, dims.w, item.l)),
        w: Math.max(0.5, resolveDimension(params, dims.l, item.w)),
        h: Math.max(0.1, resolveDimension(params, dims.h, item.h)),
        power: Math.max(0, firstPower(params, powerKeysForLabel(item.label))),
        rotation: 0,
        urlImportKey: item.label,
        topologyLabel: item.label,
        ...thermal
      };
    });
  }

  async function loadLayouts() {
    if (layoutsCache) return layoutsCache;
    const response = await fetch("topology_layouts.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Could not load topology_layouts.json.");
    }
    layoutsCache = await response.json();
    return layoutsCache;
  }

  const TOPOLOGY_ALIASES = {
    // DiscoverEE short title for the multi-diode boost layout (id=31 style URLs).
    "pfc boost converter": "Two Switch Boost Converter",
    "totempole pfc boost converter": "Totempole PFC Boost converter"
  };

  function findLayout(title, layouts) {
    const normalized = normalizeTopologyTitle(title);
    const aliasTarget = TOPOLOGY_ALIASES[normalized.toLowerCase()];
    if (aliasTarget && layouts[aliasTarget]) {
      return layouts[aliasTarget];
    }
    if (layouts[normalized]) return layouts[normalized];
    const underscored = normalized.replace(/ /g, "_");
    if (layouts[underscored]) return layouts[underscored];
    const lower = normalized.toLowerCase();
    for (const key of Object.keys(layouts)) {
      if (key.toLowerCase() === lower) return layouts[key];
    }
    return null;
  }

  function collectMetadata(params) {
    const metadata = {
      discovereeId: getParam(params, "id") || null,
      topologyTitle: getParam(params, "topology_title") || null,
      username: getParam(params, "username") || null
    };
    if (!isMissingValue(getParam(params, "fs"))) metadata.fs = getParam(params, "fs");
    if (!isMissingValue(getParam(params, "fsw"))) metadata.fsw = getParam(params, "fsw");
    if (!isMissingValue(getParam(params, "Vin[V_DC]_key"))) metadata.vin = getParam(params, "Vin[V_DC]_key");
    if (!isMissingValue(getParam(params, "Vout[V_DC]_key"))) metadata.vout = getParam(params, "Vout[V_DC]_key");
    if (!isMissingValue(getParam(params, "Iout[A_DC]_key"))) metadata.iout = getParam(params, "Iout[A_DC]_key");
    return metadata;
  }

  function collectGlobals(params) {
    const globals = { importDefaults: [] };
    const ambientRaw =
      getParam(params, "T_AMBIENT") ??
      getParam(params, "ambient_c") ??
      getParam(params, "ambient");
    if (isMissingValue(ambientRaw)) {
      globals.ambientC = DEFAULT_AMBIENT_C;
      globals.importDefaults.push("T_AMBIENT");
    } else {
      const ambient = parseOptionalNumber(ambientRaw);
      if (ambient !== null) {
        globals.ambientC = ambient;
      } else {
        globals.ambientC = DEFAULT_AMBIENT_C;
        globals.importDefaults.push("T_AMBIENT");
      }
    }
    return globals;
  }

  async function parseTopologyImport(params, marginMm) {
    const title = getParam(params, "topology_title");
    if (!title || !String(title).trim()) {
      throw new Error("topology_title is missing from the URL.");
    }
    const layouts = await loadLayouts();
    const layout = findLayout(title, layouts);
    if (!layout || !Array.isArray(layout.components) || !layout.components.length) {
      throw new Error(`Unknown topology_title "${title}". No matching layout was found.`);
    }
    const components = topologyToBoardComponents(layout.components, params, marginMm);
    return {
      globals: collectGlobals(params),
      metadata: collectMetadata(params),
      components,
      params,
      layoutTitle: layout.title,
      layoutFile: layout.htmlFile
    };
  }

  function globalRthCaStatus(params) {
    let keyFound = false;
    let empty = false;
    let valid = false;
    let emptyKeyName = "RthCA";
    const source = params || {};
    for (const key of Object.keys(source)) {
      if (!/^rth_?ca(\[\])?$/i.test(key) && key.toLowerCase() !== "rthca") {
        continue;
      }
      keyFound = true;
      emptyKeyName = key;
      if (isMissingValue(source[key])) {
        empty = true;
      } else {
        const value = parseOptionalNumber(source[key]);
        if (value !== null && value > 0) {
          valid = true;
        } else {
          empty = true;
        }
      }
    }
    return { keyFound, empty, valid, emptyKeyName };
  }

  function validateTopologyImport(parsed) {
    const errors = [];
    const warnings = [];
    const info = [];

    if (!parsed.components.length) {
      errors.push("No components were found in the layout.");
      return { ok: false, errors, warnings, info };
    }

    parsed.components.forEach(component => {
      if (component.rthMissing) {
        warnings.push(`${component.name}: Rth is missing or invalid. Enter Rth in the form before Run Simulation.`);
      }
    });

    const rthStatus = globalRthCaStatus(parsed.params);
    if (!rthStatus.valid) {
      if (rthStatus.keyFound && rthStatus.empty) {
        info.push(`${rthStatus.emptyKeyName} was empty — using default 1.`);
      } else if (!rthStatus.keyFound) {
        info.push("No Rth in URL — using default 1.");
      }
    }
    if (parsed.globals && Array.isArray(parsed.globals.importDefaults) && parsed.globals.importDefaults.includes("T_AMBIENT")) {
      info.push("T_AMBIENT was empty — using 25°C.");
    }

    return { ok: errors.length === 0, errors, warnings, info };
  }

  function hasTopologyTitle(params) {
    const title = getParam(params, "topology_title");
    return Boolean(title && String(title).trim());
  }

  global.TopologyImport = {
    hasTopologyTitle,
    loadLayouts,
    findLayout,
    parseTopologyImport,
    validateTopologyImport,
    topologyToBoardComponents
  };
})(window);
