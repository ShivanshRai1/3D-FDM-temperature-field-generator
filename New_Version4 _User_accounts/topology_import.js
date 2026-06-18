/**
 * DiscoverEE topology_title import: component X/Y from topology layouts,
 * dimensions and power from URL parameters.
 */
(function (global) {
  "use strict";

  const MAX_REASONABLE_POWER_W = 5000;
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

  function rthKeysForLabel(label) {
    if (/^[QD]\d+$/.test(label)) {
      return { ja: `RthJA_${label}`, jc: `RthJC_${label}`, ca: `RthCA_${label}` };
    }
    return { ja: null, jc: null, ca: null };
  }

  function missingThermal(mode, primary, secondary) {
    return {
      rthMode: mode,
      rth: Math.max(0.1, primary || 25),
      rthSecondary: secondary ?? null,
      rthCaseToAmbient: mode === "junction_to_case_to_ambient" ? secondary ?? null : null,
      rthCaseTemperatureC: null,
      rthMissing: true
    };
  }

  function resolveThermal(params, label) {
    const keys = rthKeysForLabel(label);
    const globalCa = parseOptionalNumber(getParam(params, "RthCA"));

    if (keys.ja && !isMissingValue(getParam(params, keys.ja))) {
      const raw = getParam(params, keys.ja);
      const value = parseOptionalNumber(raw);
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
      if (!isMissingValue(raw)) return missingThermal("junction_to_ambient", 25, null);
    }

    const jcPresent = keys.jc && !isMissingValue(getParam(params, keys.jc));
    const caPresent = (keys.ca && !isMissingValue(getParam(params, keys.ca))) || globalCa !== null;
    const jc = jcPresent ? parseOptionalNumber(getParam(params, keys.jc)) : null;
    const ca = keys.ca && !isMissingValue(getParam(params, keys.ca))
      ? parseOptionalNumber(getParam(params, keys.ca))
      : globalCa;

    if (jcPresent && caPresent && jc !== null && jc > 0 && ca !== null && ca > 0) {
      return {
        rthMode: "junction_to_case_to_ambient",
        rth: jc,
        rthSecondary: ca,
        rthCaseToAmbient: ca,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }
    if (caPresent && ca !== null && ca > 0) {
      return {
        rthMode: "junction_to_ambient",
        rth: ca,
        rthSecondary: null,
        rthCaseToAmbient: null,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }
    if (jcPresent && jc !== null && jc > 0) {
      return {
        rthMode: "junction_to_ambient",
        rth: jc,
        rthSecondary: null,
        rthCaseToAmbient: null,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
    }
    if ((jcPresent && !isMissingValue(getParam(params, keys.jc))) || (keys.ca && !isMissingValue(getParam(params, keys.ca)))) {
      return missingThermal("junction_to_case_to_ambient", jc || 1, ca || 1);
    }

    return missingThermal("junction_to_ambient", 25, null);
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

  function findLayout(title, layouts) {
    const normalized = normalizeTopologyTitle(title);
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
      globals: {},
      metadata: collectMetadata(params),
      components,
      params,
      layoutTitle: layout.title,
      layoutFile: layout.htmlFile
    };
  }

  function validateTopologyImport(parsed) {
    const errors = [];
    const warnings = [];

    if (!parsed.components.length) {
      errors.push("Topology layout did not produce any components.");
      return { ok: false, errors, warnings };
    }

    parsed.components.forEach(component => {
      if (component.rthMissing) {
        warnings.push(
          `${component.name}: thermal resistance is missing or invalid in the URL. Complete the selected Rth path in the UI before running.`
        );
      }
      if (component.power <= 0) {
        warnings.push(`${component.name}: power loss is zero or missing in the URL.`);
      }
    });

    return { ok: errors.length === 0, errors, warnings };
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
