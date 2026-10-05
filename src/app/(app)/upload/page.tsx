import { UploadWizard } from "@/components/upload-wizard";

export default async function UploadPage({ searchParams }: PageProps<"/upload">) {
  const { step, case: caseParam } = await searchParams;
  const initial = Number(step);
  const initialStep = initial === 2 || initial === 3 ? initial : 1;
  const initialCaseId = typeof caseParam === "string" ? caseParam : undefined;
  return <UploadWizard key={`${initialStep}-${initialCaseId ?? ""}`} initialStep={initialStep} initialCaseId={initialCaseId} />;
}
