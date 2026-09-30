import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Evidence-Aware AI Research Assistant | Scientific Literature Analysis',
  description:
    'Transform uploaded scientific PDFs into a unified, evidence-aware literature review with interactive comparison tables and verifiable citations.',
  keywords: [
    'literature review',
    'research assistant',
    'scientific papers',
    'evidence-aware',
    'RAG',
    'AI',
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-surface-950">{children}</body>
    </html>
  );
}
