"use client";
import DataTable from "@/components/DataTable";
import { useApi } from "@/lib/api";
import { date, short } from "@/lib/labels";
import { fmtAmt } from "@/lib/chain";

void date; void short; void fmtAmt;
export default function Page() {
  const { data } = useApi<any[]>("/admin/users", 10000);
  return <div className="space-y-4"><h1>Users</h1><DataTable rows={data} cols={[{ key: "email", label: "Email" }, { key: "name", label: "Name" }, { key: "handle", label: "Username" }, { key: "phone", label: "Phone" }, { key: "heard_from", label: "Heard from", render: (r) => r.heard_from === "other" ? `other: ${r.heard_other ?? ""}` : r.heard_from ?? "" }, { key: "wallet", label: "Wallet", render: (r) => short(r.wallet, 4) }, { key: "is_admin", label: "Admin", render: (r) => (r.is_admin ? "Yes" : "") }, { key: "created_at", label: "Joined", render: (r) => date(r.created_at) }]} /></div>;
}
