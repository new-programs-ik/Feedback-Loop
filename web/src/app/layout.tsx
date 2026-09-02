import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Feedback Loop — Interview Kickstart", template: "%s · Feedback Loop" },
  description:
    "Turns a low-rated class recording into ready-to-send instructor feedback — drafted by AI, approved by a human.",
  icons: { icon: "/icon.svg" },
};

// Runs synchronously in <head>, before first paint, so a dark-mode user never sees a light flash.
// (The inline-script pattern from Next's preventing-flash guide, adapted to our `.dark` class.)
// theme: "light" | "dark" | unset (= follow the OS). The toggle in the topbar writes the same key.
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("theme");var d=t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches);var c=document.documentElement.classList;d?c.add("dark"):c.remove("dark");document.documentElement.style.colorScheme=d?"dark":"light"}catch(e){}})()`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
