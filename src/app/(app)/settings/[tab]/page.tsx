import { notFound } from "next/navigation";
import { Settings } from "@/components/settings";
import { SETTINGS_TABS, type SettingsTab } from "@/lib/data";

export function generateStaticParams() {
  return SETTINGS_TABS.map((t) => ({ tab: t.k }));
}

export default async function SettingsPage({ params }: PageProps<"/settings/[tab]">) {
  const { tab } = await params;
  if (!SETTINGS_TABS.some((t) => t.k === tab)) notFound();
  return <Settings tab={tab as SettingsTab} />;
}
