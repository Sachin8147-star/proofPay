import { defineChain } from "viem";
import { createConfig, http } from "wagmi";
import { injected } from "@wagmi/core";
import abi from "./abi.json";
import { EXPLORER, SYMBOL } from "./format";

export { EXPLORER, SYMBOL, addrUrl, fmtAmt, fmtWei, txUrl } from "./format";

const RPC = process.env.NEXT_PUBLIC_MST_RPC_URL ?? "https://testnetrpc.mstblockchain.com";
export const ESCROW = (process.env.NEXT_PUBLIC_ESCROW_ADDRESS ?? "") as `0x${string}`;
export const ABI = abi as any;

export const mst = defineChain({
  id: Number(BigInt(process.env.NEXT_PUBLIC_MST_CHAIN_ID ?? "0x5752035")),
  name: "MST Testnet",
  nativeCurrency: { name: SYMBOL, symbol: SYMBOL, decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
  blockExplorers: { default: { name: "MSTScan", url: EXPLORER } },
});

export const wagmiConfig = createConfig({ chains: [mst], connectors: [injected()], transports: { [mst.id]: http(RPC) }, ssr: true });

