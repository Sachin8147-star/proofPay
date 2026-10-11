"use client";
import { useState } from "react";
import { useAccount, usePublicClient, useSwitchChain, useWriteContract } from "wagmi";
import { ABI, ESCROW, mst } from "@/lib/chain";

/** Runs an on-chain call from the connected wallet, waits for the receipt, and reports a readable error. */
export function useTx() {
  const { address, chainId } = useAccount();
  const { switchChainAsync } = useSwitchChain();
  const { writeContractAsync } = useWriteContract();
  const pc = usePublicClient({ chainId: mst.id });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(label: string, fn: string, args: unknown[], expect?: string | null, value?: bigint): Promise<string | null> {
    setError(null);
    try {
      if (!ESCROW) throw new Error("Payments are not configured. Set NEXT_PUBLIC_ESCROW_ADDRESS after deploying the escrow contract.");
      if (!address) throw new Error("Connect your wallet first.");
      if (expect && address.toLowerCase() !== expect.toLowerCase()) throw new Error(`Switch your wallet to the account ${expect.slice(0, 6)}…${expect.slice(-4)} for this step.`);
      setBusy(label);
      if (chainId !== mst.id) await switchChainAsync({ chainId: mst.id });
      const hash = await writeContractAsync({ address: ESCROW, abi: ABI, functionName: fn, args, value, chainId: mst.id });
      const rc = await pc!.waitForTransactionReceipt({ hash });
      if (rc.status !== "success") throw new Error("The transaction failed on-chain.");
      return hash;
    } catch (e: any) {
      setError((e?.shortMessage ?? e?.message ?? "Transaction failed").split("\n")[0]);
      return null;
    } finally {
      setBusy(null);
    }
  }
  return { send, busy, error, setError };
}
