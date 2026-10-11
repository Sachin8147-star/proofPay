import solc from "solc";
import fs from "fs";
import path from "path";

const source = fs.readFileSync("contracts/ProofPayEscrow.sol", "utf8");
const input = {
  language: "Solidity",
  sources: { "ProofPayEscrow.sol": { content: source } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    evmVersion: "paris", // no PUSH0: safest for chains that have not enabled Shanghai
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
  },
};
const findImports = (p) => {
  try { return { contents: fs.readFileSync(path.join("node_modules", p), "utf8") }; }
  catch { return { error: `not found: ${p}` }; }
};
const out = JSON.parse(solc.compile(JSON.stringify(input), { import: findImports }));
const errors = (out.errors || []).filter((e) => e.severity === "error");
(out.errors || []).forEach((e) => console.error(e.formattedMessage));
if (errors.length) process.exit(1);

const c = out.contracts["ProofPayEscrow.sol"].ProofPayEscrow;
const artifact = { abi: c.abi, bytecode: "0x" + c.evm.bytecode.object };
fs.mkdirSync("artifacts", { recursive: true });
fs.writeFileSync("artifacts/ProofPayEscrow.json", JSON.stringify(artifact, null, 2));
for (const dest of ["../backend/app/abi.json", "../web/lib/abi.json"]) {
  if (fs.existsSync(path.dirname(dest))) fs.writeFileSync(dest, JSON.stringify(c.abi));
}
console.log(`compiled: ${(artifact.bytecode.length - 2) / 2} bytes`);
