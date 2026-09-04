import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "The Lenny Growth Assistant | Podcast Knowledge Base & Ship 30",
  description:
    "Conversational AI assistant grounded strictly in Lenny's Podcast transcripts. Query tactical product management advice and generate publish-ready Ship 30 essays.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="h-full bg-zinc-950 text-zinc-100 overflow-hidden font-sans">
        {children}
      </body>
    </html>
  );
}
