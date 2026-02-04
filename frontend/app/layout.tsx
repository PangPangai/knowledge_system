import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Knowledge Base - AI Assistant",
  description: "Intelligent knowledge base system powered by RAG",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="animated-bg">
        {children}
      </body>
    </html>
  );
}
