"use client";
import { useState } from "react";
import { useAccount, useBalance, useConnect, useDisconnect, useSignMessage, useSwitchChain } from "wagmi";
import { api, useApi } from "@/lib/api";
import { SYMBOL, mst } from "@/lib/chain";
import { short } from "@/lib/labels";
import { AddrLink, Err } from "./ui";

export default function WalletBar() {
  const { address, isConnected, chainId } = useAccount();
  const { connectors, connect, error: cErr } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();
  const { signMessageAsync } = useSignMessage();
  const { data: bal } = useBalance({ address, chainId: mst.id });
  const { data: me, mutate } = useApi<any>("/me");
  const [err, setErr] = useState<string>();

  async function link() {
    setErr(undefined);
    try {
      const { data } = await (await import("@/lib/supabase")).supabase().auth.getUser();
      const message = `Link this wallet to my ProofPay account.\nUser: ${data.user!.id}\nAddress: ${address}\nIssued: ${new Date().toISOString()}`;
      await api("/me/wallet", { body: { address, message, signature: await signMessageAsync({ message }) } });
      mutate();
    } catch (e: any) { setErr(e.shortMessage ?? e.message); }
  }

  if (!isConnected)
    return (
      <div className="space-y-2">
        <button className="btn-primary w-full" onClick={() => connect({ connector: connectors[0] })}>Connect wallet</button>
        {!connectors.length || cErr ? <Err>No browser wallet found. Install MetaMask to continue.</Err> : null}
      </div>
    );
  const linked = me?.wallet && address && me.wallet === address.toLowerCase();
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between"><AddrLink a={address} /><button className="link text-xs" onClick={() => disconnect()}>Disconnect</button></div>
      <p className="font-semibold">{bal ? `${Number(bal.formatted).toLocaleString(undefined, { maximumFractionDigits: 4 })} ${SYMBOL}` : "…"}</p>
      {chainId !== mst.id && <button className="btn-ghost w-full" onClick={() => switchChain({ chainId: mst.id })}>Switch to MST Testnet</button>}
      {me && !linked && <button className="btn-ghost w-full" onClick={link}>{me.wallet ? `Replace linked wallet (${short(me.wallet, 4)})` : "Link this wallet to your account"}</button>}
      <Err>{err}</Err>
    </div>
  );
}
