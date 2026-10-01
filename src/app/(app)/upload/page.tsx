import { UploadWizard } from "@/components/upload-wizard";

export default async function UploadPage({ searchParams }: PageProps<"/upload">) {
  const { step } = await searchParams;
  const initial = Number(step);
  const initialStep = initial === 2 || initial === 3 ? initial : 1;
  return <UploadWizard key={initialStep} initialStep={initialStep} />;
}
