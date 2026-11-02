import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "AI 课程工作室 · 对话即作者",
  description:
    "以对话为中心、以课程为活文档的 AI 课程创作工作台——检索取证、逐讲生成、追问修改、版本可回溯。",
};

const themeScript = `(function(){try{var stored=localStorage.getItem("course-studio-theme");var dark=stored?stored==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;if(dark){document.documentElement.classList.add("dark");}}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <div className="app-backdrop" aria-hidden />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
