import { formatEther } from "viem";

export const EXPLORER = process.env.NEXT_PUBLIC_MST_EXPLORER_URL ?? "https://testnet.mstscan.com";
export const SYMBOL = process.env.NEXT_PUBLIC_MST_SYMBOL ?? "MST";
export const txUrl = (h: string) => `${EXPLORER}/tx/${h}`;
export const addrUrl = (a: string) => `${EXPLORER}/address/${a}`;
export const fmtWei = (wei: bigint | string) => `${Number(formatEther(BigInt(wei))).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${SYMBOL}`;
export const fmtAmt = (a: string | number) => `${Number(a).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${SYMBOL}`;
