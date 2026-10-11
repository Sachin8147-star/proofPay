"use client";
import DataTable from "@/components/DataTable";
import { useApi } from "@/lib/api";
import { date, short } from "@/lib/labels";
import { fmtAmt } from "@/lib/chain";

void date; void short; void fmtAmt;
export default function Page() {
  const { data } = useApi<any[]>("/admin/contracts", 10000);
  return <div className="space-y-4"><h1>Contracts</h1><DataTable rows={data} cols={[{ key: "title", label: "Title" }, { key: "status", label: "Status" }, { key: "total_amount", label: "Total", render: (r) => fmtAmt(r.total_amount) }, { key: "escrow_id", label: "Escrow", render: (r) => <span className="chip">{short(r.escrow_id, 6)}</span> }, { key: "created_at", label: "Created", render: (r) => date(r.created_at) }]} /></div>;
}
