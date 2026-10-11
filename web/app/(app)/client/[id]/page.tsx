import ContractView from "@/components/ContractView";
export default function Page({ params }: { params: { id: string } }) { return <ContractView id={params.id} />; }
