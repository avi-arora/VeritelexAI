import { redirect } from "next/navigation";

export default async function CasePage({ params }: PageProps<"/cases/[caseId]">) {
  const { caseId } = await params;
  redirect(`/cases/${caseId}/background`);
}
