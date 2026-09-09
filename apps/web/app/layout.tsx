import type { Metadata } from "next";

import { Shell } from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Atlas — Real Estate Investment Intelligence",
  description:
    "Underwrite a property across wholesale, flip, buy & hold, BRRRR and seller financing, and see which strategy it actually supports.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
