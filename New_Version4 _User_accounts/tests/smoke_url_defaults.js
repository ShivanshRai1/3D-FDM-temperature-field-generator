const fs = require("fs");
const vm = require("vm");

function loadModule(file) {
  const sandbox = { console, fetch: async () => ({ ok: true, json: async () => ({}) }) };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(file, "utf8"), sandbox);
  return sandbox;
}

function testTopology(file, label) {
  const mod = loadModule(file).TopologyImport;
  const params = {
    "Rth_ca[]": "",
    T_AMBIENT: "",
    RthJC_D1: "",
    RthJA_D1: "-",
    D1_PL: "0.2",
    pl: '[[10,10,5,1,1,"D1"],[10,10,5,2,2,"Cout"]]'
  };
  const components = mod.topologyToBoardComponents(
    [
      { label: "D1", x: 0, z: 0, l: 10, w: 10, h: 5 },
      { label: "Cout", x: 1, z: 1, l: 10, w: 10, h: 5 }
    ],
    params,
    8
  );
  const validation = mod.validateTopologyImport({
    params,
    components,
    globals: { importDefaults: ["T_AMBIENT"], ambientC: 25 }
  });
  const issues = [];
  if (components.some((component) => component.rthMissing)) {
    issues.push("rthMissing");
  }
  if (validation.warnings.length) {
    issues.push(`warnings=${validation.warnings.length}`);
  }
  if (!validation.info.length) {
    issues.push("missing info defaults");
  }
  console.log(`${label}: ${issues.length ? issues.join(", ") : "OK"}`);
  return issues.length === 0;
}

function testUrlImport(file, label) {
  const sandbox = loadModule(file);
  const params = {
    import: "1",
    W_Q1: "10",
    L_Q1: "15",
    H_Q1: "4.4",
    PLoss_Q1: "3",
    RthCA: "",
    t_ambient: ""
  };
  const parsed = sandbox.UrlImport.parseUrlImport(params);
  const validation = sandbox.UrlImport.validateUrlImport(parsed);
  const issues = [];
  if (parsed.components.some((component) => component.rthMissing)) {
    issues.push("rthMissing");
  }
  if (validation.warnings.length) {
    issues.push(`warnings=${validation.warnings.length}`);
  }
  if (!parsed.components.length) {
    issues.push("no components");
  }
  console.log(`${label}: ${issues.length ? issues.join(", ") : "OK"}`);
  return issues.length === 0;
}

const ok = [
  testTopology("topology_import.js", "V1 topology defaults"),
  testTopology("topology_import_v2.js", "V2 topology defaults"),
  testUrlImport("url_import.js", "V1 legacy import"),
  testUrlImport("url_import_v2.js", "V2 legacy import")
].every(Boolean);

process.exit(ok ? 0 : 1);
