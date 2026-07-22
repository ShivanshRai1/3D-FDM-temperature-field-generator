/**
 * V2 copy — topology / layout import for pcb_temperature_app_v2.html.
 * Keep V1 (topology_import.js) unchanged.
 *
 * V2 URL format (DiscoverEE):
 *   pl=[[l,w,h,x,z,"Label"], ...]
 *   Q1_PL / D1_PL / Cin_PL / ...  (signed; thermal uses abs)
 *   T_AMBIENT=25
 *   Rth_ca[]=1
 *
 * If pl= / *_PL are absent, falls back to V1 topology_layouts.json + PLoss_* behavior.
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

  /** V2: DiscoverEE may send signed *_PL; thermal dissipation uses absolute watts. */
  function parseV2Power(raw) {
    const value = parseOptionalNumber(raw);
    if (value === null) return null;
    const abs = Math.abs(value);
    if (abs > MAX_REASONABLE_POWER_W) return null;
    return abs;
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

  function powerForLabel(params, label) {
    const fromPl = parseV2Power(getParam(params, `${label}_PL`));
    if (fromPl !== null) return fromPl;
    return firstPower(params, powerKeysForLabel(label));
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
        const value = parseOptionalNumber(params[key]);
        if (value !== null && value > 0) return value;
      }
    }
    return parseOptionalNumber(getParam(params, "RthCA"));
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
    const globalCa = getGlobalRthCa(params);
    const jaEntry = firstParamRaw(params, keys.ja);

    if (jaEntry.key && !isMissingValue(jaEntry.raw)) {
      const value = parseOptionalNumber(jaEntry.raw);
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
      if (!isMissingValue(jaEntry.raw)) {
        return missingThermal("junction_to_ambient", 25, null);
      }
    }

    const jcEntry = firstParamRaw(params, keys.jc);
    const caEntry = firstParamRaw(params, keys.ca);
    const jcPresent = jcEntry.key !== null && !isMissingValue(jcEntry.raw);
    const caPresent = (caEntry.key !== null && !isMissingValue(caEntry.raw)) || globalCa !== null;
    const jc = jcPresent ? parseOptionalNumber(jcEntry.raw) : null;
    const ca = caEntry.key !== null && !isMissingValue(caEntry.raw)
      ? parseOptionalNumber(caEntry.raw)
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
    if ((jcEntry.key !== null && !isMissingValue(jcEntry.raw)) || (caEntry.key !== null && !isMissingValue(caEntry.raw))) {
      return missingThermal("junction_to_case_to_ambient", jc || 1, ca || 1);
    }
    if (globalCa !== null && globalCa > 0) {
      return {
        rthMode: "junction_to_ambient",
        rth: globalCa,
        rthSecondary: null,
        rthCaseToAmbient: null,
        rthCaseTemperatureC: null,
        rthMissing: false
      };
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

  function hasV2PlFormat(params) {
    if (!isMissingValue(getParam(params, "pl"))) return true;
    return Object.keys(params).some(key => /_PL$/i.test(key));
  }

  function stripJsComments(text) {
    return String(text)
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n\r]*/g, "");
  }

  function parsePlLayout(raw) {
    const cleaned = stripJsComments(raw).trim();
    let data;
    try {
      data = JSON.parse(cleaned);
    } catch (error) {
      throw new Error("Could not parse pl= layout array from the URL. Expected a JSON array of [l, w, h, x, z, \"Label\"].");
    }
    if (!Array.isArray(data) || !data.length) {
      throw new Error("pl= layout array is empty.");
    }
    return data.map((row, index) => {
      if (!Array.isArray(row) || row.length < 6) {
        throw new Error(`pl= row ${index + 1} is invalid. Expected [l, w, h, x, z, "Label"].`);
      }
      const l = Number(row[0]);
      const w = Number(row[1]);
      const h = Number(row[2]);
      const x = Number(row[3]);
      const z = Number(row[4]);
      const label = String(row[5] ?? "").trim();
      if (!label || ![l, w, h, x, z].every(Number.isFinite)) {
        throw new Error(`pl= row ${index + 1} ("${label || "?"}") has invalid numeric values.`);
      }
      return { label, l, w, h, x, z };
    });
  }

  function collectGlobalsV2(params) {
    const globals = {};
    const ambient =
      parseOptionalNumber(getParam(params, "T_AMBIENT")) ??
      parseOptionalNumber(getParam(params, "ambient_c")) ??
      parseOptionalNumber(getParam(params, "ambient"));
    if (ambient !== null) {
      globals.ambientC = ambient;
    }
    return globals;
  }

  function layoutItemsToBoardComponents(layoutComponents, params, marginMm, usePlSizes) {
    const boardPoints = layoutComponents.map(item => ({ x: item.x, y: -item.z }));
    const minX = Math.min(...boardPoints.map(point => point.x));
    const minY = Math.min(...boardPoints.map(point => point.y));
    const margin = Math.max(0, marginMm || 8);

    return layoutComponents.map((item, index) => {
      const dims = dimensionKeysForLabel(item.label);
      const thermal = resolveThermal(params, item.label);
      const point = boardPoints[index];
      const l = usePlSizes
        ? Math.max(0.5, item.l)
        : Math.max(0.5, resolveDimension(params, dims.w, item.l));
      const w = usePlSizes
        ? Math.max(0.5, item.w)
        : Math.max(0.5, resolveDimension(params, dims.l, item.w));
      const h = usePlSizes
        ? Math.max(0.1, item.h)
        : Math.max(0.1, resolveDimension(params, dims.h, item.h));
      return {
        id: componentId(item.label, index),
        name: displayName(item.label),
        label: item.label,
        x: point.x - minX + margin,
        y: point.y - minY + margin,
        l,
        w,
        h,
        power: Math.max(0, powerForLabel(params, item.label)),
        rotation: 0,
        urlImportKey: item.label,
        topologyLabel: item.label,
        ...thermal
      };
    });
  }

  function topologyToBoardComponents(layoutComponents, params, marginMm) {
    return layoutItemsToBoardComponents(layoutComponents, params, marginMm, false);
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
      username: getParam(params, "username") || null,
      importVersion: hasV2PlFormat(params) ? "v2" : "v1"
    };
    if (!isMissingValue(getParam(params, "fs"))) metadata.fs = getParam(params, "fs");
    if (!isMissingValue(getParam(params, "fsw"))) metadata.fsw = getParam(params, "fsw");
    if (!isMissingValue(getParam(params, "Vin[V_DC]_key"))) metadata.vin = getParam(params, "Vin[V_DC]_key");
    if (!isMissingValue(getParam(params, "Vout[V_DC]_key"))) metadata.vout = getParam(params, "Vout[V_DC]_key");
    if (!isMissingValue(getParam(params, "Iout[A_DC]_key"))) metadata.iout = getParam(params, "Iout[A_DC]_key");
    if (!isMissingValue(getParam(params, "T_AMBIENT"))) metadata.tAmbient = getParam(params, "T_AMBIENT");
    return metadata;
  }

  async function parseTopologyImport(params, marginMm) {
    const plRaw = getParam(params, "pl");

    // V2 primary path: layout embedded in URL as pl=
    if (!isMissingValue(plRaw)) {
      const layoutComponents = parsePlLayout(plRaw);
      const components = layoutItemsToBoardComponents(layoutComponents, params, marginMm, true);
      const title = getParam(params, "topology_title");
      return {
        globals: collectGlobalsV2(params),
        metadata: collectMetadata(params),
        components,
        params,
        layoutTitle: title && String(title).trim() ? String(title).trim() : "URL pl layout",
        layoutFile: null,
        importVersion: "v2"
      };
    }

    // Fallback: topology_layouts.json (V1-style), with optional *_PL power keys
    const title = getParam(params, "topology_title");
    if (!title || !String(title).trim()) {
      throw new Error("topology_title is missing from the URL (and no pl= layout was provided).");
    }
    const layouts = await loadLayouts();
    const layout = findLayout(title, layouts);
    if (!layout || !Array.isArray(layout.components) || !layout.components.length) {
      throw new Error(
        `Unknown topology_title "${title}". No matching layout was found, and no pl= array was provided in the URL.`
      );
    }
    const components = layoutItemsToBoardComponents(layout.components, params, marginMm, false);
    return {
      globals: collectGlobalsV2(params),
      metadata: collectMetadata(params),
      components,
      params,
      layoutTitle: layout.title,
      layoutFile: layout.htmlFile,
      importVersion: hasV2PlFormat(params) ? "v2" : "v1"
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

  function shouldHandleImport(params) {
    return hasTopologyTitle(params) || hasV2PlFormat(params);
  }

  global.TopologyImport = {
    hasTopologyTitle,
    hasV2PlFormat,
    shouldHandleImport,
    loadLayouts,
    findLayout,
    parseTopologyImport,
    validateTopologyImport,
    topologyToBoardComponents,
    parsePlLayout
  };
})(window);
