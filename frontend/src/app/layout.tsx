import type { Metadata, Viewport } from "next";
import { Inter, Inter_Tight, IBM_Plex_Mono, Silkscreen } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["400", "500", "600", "700"],
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  weight: ["500", "600", "700", "800"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-ibm",
  weight: ["400", "500", "600"],
});

const silkscreen = Silkscreen({
  subsets: ["latin"],
  variable: "--font-pixel",
  weight: ["400"],
});

export const metadata: Metadata = {
  title: "SPIRAL AI — Transparent AI",
  description:
    "A transparent AI chatbot that shows exactly how confident every answer is.",
};

export const viewport: Viewport = {
  themeColor: "#070708",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${interTight.variable} ${plexMono.variable} ${silkscreen.variable}`}
    >
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
