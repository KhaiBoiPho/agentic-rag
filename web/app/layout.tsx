import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./ui.css";

export const metadata: Metadata = {
  title: "Cốt — Trợ lý dự toán & vật liệu xây dựng",
  description:
    "Trợ lý AI cho vật liệu xây dựng Việt Nam: RAG, dự toán chi phí, tìm kiếm & nghiên cứu web, giọng nói.",
};

export const viewport: Viewport = {
  themeColor: "#2648D8",
  width: "device-width",
  initialScale: 1,
};

// Apply the stored theme before first paint to avoid a flash.
const themeInit = `(function(){try{var t=localStorage.getItem('cot.theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
