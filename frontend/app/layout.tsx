import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin', 'vietnamese'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: 'Agentic RAG — Trợ lý vật liệu xây dựng',
  description: 'Trợ lý AI RAG cho vật liệu xây dựng Việt Nam',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={inter.variable}>
      <body className="h-full bg-canvas text-ink antialiased dark:bg-[#212121] dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
