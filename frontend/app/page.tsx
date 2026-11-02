export default function Home() {
  return (
    <main className="page">
      <div className="card">
        <h1>AI 课程工作室</h1>
        <p className="tagline">
          以对话为中心、以课程为活文档的创作工作台
        </p>
        <p className="hint">
          M0 脚手架已就绪：后端 FastAPI（Port/Adapter 可插拔）、前端 Next.js。
          后端健康检查见 <code>/health</code>，API 文档见 <code>/docs</code>。
        </p>
        <ul className="features">
          <li>成体系生成课程（human-in-the-loop，逐讲审核）</li>
          <li>追问与修改（Ask &amp; Amend），可 diff、可回滚</li>
          <li>知识源检索（RAG）与幻觉抑制（强制引用）</li>
        </ul>
      </div>
    </main>
  );
}
