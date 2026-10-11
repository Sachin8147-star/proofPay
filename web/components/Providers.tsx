"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, ReactNode } from "react";
import { WagmiProvider } from "wagmi";
import { wagmiConfig } from "@/lib/chain";

export default function Providers({ children }: { children: ReactNode }) {
  const [qc] = useState(() => new QueryClient());
  return <WagmiProvider config={wagmiConfig}><QueryClientProvider client={qc}>{children}</QueryClientProvider></WagmiProvider>;
}
