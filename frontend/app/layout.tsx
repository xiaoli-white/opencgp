import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 课程工作室",
  description:
    "以对话为中心、以课程为活文档的 AI 课程创作工作台——AI 当作者兼助教，人在关键处拍板。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
