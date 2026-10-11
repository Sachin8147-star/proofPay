import HelpChat from "@/components/HelpChat";
export default function Help() {
  return <div className="max-w-2xl space-y-4"><div><h1>Help</h1><p className="mt-1 text-sm text-mute">Our AI assistant explains how ProofPay works and helps you fix problems. It cannot see your account or move money.</p></div><HelpChat /></div>;
}
