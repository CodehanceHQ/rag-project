import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Local RAG Studio",
  description: "Inspect document ingestion and semantic vector retrieval",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

