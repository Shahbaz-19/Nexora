import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { AuthProvider } from "@/context/AuthContext";

import "./globals.css";


const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});


export const metadata: Metadata = {
  applicationName: "Nexora",
  title: {
    default: "Nexora — Intelligence, connected.",
    template: "%s | Nexora",
  },
  description: "AI-Powered Knowledge Intelligence Platform",
  openGraph: {
    type: "website",
    title: "Nexora — Intelligence, connected.",
    siteName: "Nexora",
    description: "AI-Powered Knowledge Intelligence Platform",
  },
  icons: { icon: "/icon.svg" },
};


export default function RootLayout({
  children,
}: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
