import dotenv from "dotenv";
dotenv.config({ path: "../.env" });
import fs from "fs";
import { ethers } from "ethers";

const { abi, bytecode } = JSON.parse(fs.readFileSync("artifacts/ProofPayEscrow.json", "utf8"));
const provider = new ethers.JsonRpcProvider(process.env.MST_RPC_URL);
const deployer = new ethers.Wallet(process.env.DEPLOYER_PRIVATE_KEY, provider);
const verifier = new ethers.Wallet(process.env.VERIFIER_PRIVATE_KEY).address;
const arbitrator = process.env.ARBITRATOR_ADDRESS || deployer.address;
const graceSecs = BigInt(process.env.REFUND_GRACE_SECONDS || 259200);      // 3d

const net = await provider.getNetwork();
const bal = await provider.getBalance(deployer.address);
console.log(`chain ${net.chainId} | deployer ${deployer.address} | balance ${ethers.formatEther(bal)}`);
if (bal === 0n) throw new Error("Deployer has 0 balance: fund it from the MST testnet faucet first.");

const factory = new ethers.ContractFactory(abi, bytecode, deployer);
const c = await factory.deploy(deployer.address, verifier, arbitrator, graceSecs);
await c.waitForDeployment();
const address = await c.getAddress();
console.log(`ProofPayEscrow deployed: ${address}`);
console.log(`Set ESCROW_ADDRESS and NEXT_PUBLIC_ESCROW_ADDRESS to ${address}`);
