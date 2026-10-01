import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { ExportModal } from "@/components/export-modal";
import { ProtoNav } from "@/components/proto-nav";
import { Toast } from "@/components/toast";
import { StoreProvider } from "@/lib/store";
import "./globals.css";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"] });
const sourceSerif = Source_Serif_4({ variable: "--font-source-serif", subsets: ["latin"], weight: ["400", "600"], style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "VeriteLex AI",
  description: "Case files organised for the bench — chronology, issues, submissions and grounded research, every line cited.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} ${sourceSerif.variable}`}>
      <body>
        <StoreProvider>
          <div className="min-h-screen bg-paper">
            <ProtoNav />
            {children}
          </div>
          <ExportModal />
          <Toast />
        </StoreProvider>
      </body>
    </html>
  );
}
