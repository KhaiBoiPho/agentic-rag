import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

// Sohne (Stripe's proprietary display face) isn't licensable — DESIGN.md's own
// fallback guidance is Inter at weight 300 with the `ss01` stylistic set and
// tight negative tracking on display sizes, which we apply in globals.css.
const inter = Inter({
  subsets: ['latin', 'vietnamese'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: 'Agentic RAG — Trợ lý vật liệu xây dựng',
  description: 'Trợ lý AI RAG cho vật liệu xây dựng Việt Nam',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={inter.variable}>
      <body className="h-full bg-canvas-soft font-light text-ink antialiased dark:bg-slate-950 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
