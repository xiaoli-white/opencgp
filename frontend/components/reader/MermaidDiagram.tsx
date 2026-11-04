import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle } from "lucide-react";

type MermaidDiagramProps = {
  code: string;
  className?: string;
};

let renderSeq = 0;

export default function MermaidDiagram({ code, className }: MermaidDiagramProps) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [dark, setDark] = useState(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    const source = code.trim();
    if (!source) {
      setSvg("");
      setError("");
      return () => {
        aliveRef.current = false;
      };
    }
    const run = async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "loose",
          theme: dark ? "dark" : "default",
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
        });
        renderSeq += 1;
        const { svg: output } = await mermaid.render(
          `mermaid-svg-${renderSeq}`,
          source,
        );
        if (!aliveRef.current) return;
        setSvg(output);
        setError("");
      } catch (err) {
        if (!aliveRef.current) return;
        setSvg("");
        setError(err instanceof Error ? err.message : "Mermaid 渲染失败");
      }
    };
    void run();
    return () => {
      aliveRef.current = false;
    };
  }, [code, dark]);

  if (error) {
    return (
      <div className={clsx("not-prose my-4 space-y-2", className)}>
        <div className="flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/10 px-3 py-2 font-sans text-[11px] text-amber-800 dark:border-amber-300/25 dark:text-amber-200">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>图表渲染失败，已回退显示源码：{error}</span>
        </div>
        <pre className="overflow-x-auto rounded-2xl border border-white/50 bg-slate-900/90 p-3 font-mono text-[11px] leading-relaxed text-slate-100 dark:border-white/10">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div
        className={clsx(
          "my-4 flex h-24 items-center justify-center rounded-2xl border border-white/50 bg-white/50 font-sans text-[11px] text-slate-400 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-500",
          className,
        )}
      >
        正在渲染图表…
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "my-4 overflow-x-auto rounded-2xl border border-white/50 bg-white/60 p-3 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
