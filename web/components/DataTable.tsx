"use client";
import { ReactNode } from "react";
import { Empty, Loading } from "./ui";

export type Col = { key: string; label: string; render?: (row: any) => ReactNode };

export default function DataTable({ rows, cols }: { rows?: any[]; cols: Col[] }) {
  if (!rows) return <Loading />;
  if (!rows.length) return <Empty title="Nothing here yet" />;
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line text-mute"><tr>{cols.map((c) => <th key={c.key} className="px-3 py-2 font-medium">{c.label}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => <tr key={r.id ?? i}>{cols.map((c) => <td key={c.key} className="px-3 py-2 align-top">{c.render ? c.render(r) : String(r[c.key] ?? "")}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}
