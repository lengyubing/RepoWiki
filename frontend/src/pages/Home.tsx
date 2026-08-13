import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { scanProject, getWiki, getProjectInfo, listProjects, deleteProject, type ProjectInfo } from "../lib/api";
import { useWikiStore } from "../stores/wiki";
import SettingsModal from "../components/SettingsModal";

export default function Home() {
  const [url, setUrl] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [recentProjects, setRecentProjects] = useState<ProjectInfo[]>([]);
  const { loading, setLoading, scanProgress, addProgress, setProjectId, setProject, setWiki, setError, reset, settings } = useWikiStore();
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setRecentProjects).catch(() => {});
  }, [loading]);

  function formatDate(ts?: number) {
    if (!ts) return "";
    try {
      return new Date(ts * 1000).toLocaleString();
    } catch {
      return "";
    }
  }

  async function handleDeleteProject(e: React.MouseEvent, projectId: string) {
    e.stopPropagation();
    if (!confirm("Delete this project from the list? (Source files on disk are not touched.)")) return;
    await deleteProject(projectId);
    setRecentProjects((prev) => prev.filter((p) => p.id !== projectId));
  }

  async function handleRescanArchived(project: ProjectInfo) {
    // archived projects lost their wiki on restart — re-scan from the saved source
    if (!project.source) return;
    reset();
    setLoading(true);
    addProgress("Re-scanning project...");
    if (settings.apiKey) {
      localStorage.setItem("repowiki_api_key", settings.apiKey);
    }
    try {
      const info = await scanProject({
        url: project.source,
        language: settings.language,
        model: settings.model || undefined,
        api_base: settings.apiBase || undefined,
      });
      setProjectId(info.id);
      setProject(info);

      // poll status until done/error (more reliable than SSE for fast cached scans)
      const poll = async () => {
        try {
          const current = await getProjectInfo(info.id);
          if (current.status === "done") {
            const wiki = await getWiki(info.id);
            setWiki(wiki);
            addProgress("Done!");
            // brief pause so the user sees the completion before navigating
            setTimeout(() => {
              setLoading(false);
              navigate(`/project/${info.id}`);
            }, 800);
            return;
          }
          if (current.status === "error") {
            setError(current.error || "Scan failed");
            setLoading(false);
            return;
          }
          // keep polling
          setTimeout(poll, 1000);
        } catch {
          setError("Lost connection to server");
          setLoading(false);
        }
      };
      setTimeout(poll, 1000);
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  }

  function handleProjectClick(project: ProjectInfo) {
    if (project.status === "archived" && project.source) {
      handleRescanArchived(project);
    } else {
      navigate(`/project/${project.id}`);
    }
  }

  function statusLabel(status: string) {
    switch (status) {
      case "done": return { text: "Ready", cls: "bg-green-100 text-green-700" };
      case "scanning": return { text: "Scanning", cls: "bg-blue-100 text-blue-700" };
      case "pending": return { text: "Pending", cls: "bg-slate-100 text-slate-600" };
      case "error": return { text: "Error", cls: "bg-red-100 text-red-700" };
      case "archived": return { text: "Archived", cls: "bg-amber-100 text-amber-700" };
      default: return { text: status, cls: "bg-slate-100 text-slate-600" };
    }
  }

  async function handleScan() {
    if (!url.trim()) return;
    reset();
    setLoading(true);

    // save API key to localStorage for header injection
    if (settings.apiKey) {
      localStorage.setItem("repowiki_api_key", settings.apiKey);
    }

    try {
      const info = await scanProject({
        url: url.trim(),
        language: settings.language,
        model: settings.model || undefined,
        api_base: settings.apiBase || undefined,
      });
      setProjectId(info.id);
      setProject(info);

      // poll status until done/error
      const poll = async () => {
        try {
          const current = await getProjectInfo(info.id);
          if (current.status === "done") {
            const wiki = await getWiki(info.id);
            setWiki(wiki);
            addProgress("Done!");
            setTimeout(() => {
              setLoading(false);
              navigate(`/project/${info.id}`);
            }, 800);
            return;
          }
          if (current.status === "error") {
            setError(current.error || "Scan failed");
            setLoading(false);
            return;
          }
          setTimeout(poll, 1000);
        } catch {
          setError("Lost connection to server");
          setLoading(false);
        }
      };
      setTimeout(poll, 1000);
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex flex-col">
      {/* header */}
      <header className="flex items-center justify-between px-8 py-4">
        <h1 className="text-2xl font-bold text-slate-800">
          <span className="text-blue-600">Repo</span>Wiki
        </h1>
        <button
          onClick={() => setShowSettings(true)}
          className="text-slate-500 hover:text-slate-700 text-sm"
        >
          Settings
        </button>
      </header>

      {/* main content */}
      <main className="flex-1 flex flex-col items-center justify-center px-4">
        <div className="max-w-2xl w-full text-center mb-12">
          <h2 className="text-4xl font-bold text-slate-900 mb-4">
            Understand any codebase
          </h2>
          <p className="text-lg text-slate-600">
            Generate comprehensive wiki documentation with architecture diagrams,
            reading guides, and interactive Q&A.
          </p>
        </div>

        <div className="max-w-xl w-full">
          <div className="flex gap-3">
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleScan()}
              placeholder="Paste a GitHub URL or local path..."
              className="flex-1 px-4 py-3 rounded-lg border border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none text-slate-700"
              disabled={loading}
            />
            <button
              onClick={handleScan}
              disabled={loading || !url.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Scanning..." : "Generate Wiki"}
            </button>
          </div>

          {/* progress display */}
          {scanProgress.length > 0 && (
            <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4 max-h-48 overflow-y-auto">
              {scanProgress.map((step, i) => (
                <div key={i} className="text-sm text-slate-600 py-1 flex items-center gap-2">
                  <span className="text-green-500">&#10003;</span> {step}
                </div>
              ))}
              {loading && (
                <div className="text-sm text-blue-600 py-1 animate-pulse">Processing...</div>
              )}
            </div>
          )}
        </div>

        {/* recent projects */}
        {recentProjects.length > 0 && (
          <div className="max-w-3xl w-full mt-12">
            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
              Recent Projects
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {recentProjects.map((p) => {
                const badge = statusLabel(p.status);
                const isArchived = p.status === "archived";
                return (
                  <div
                    key={p.id}
                    onClick={() => handleProjectClick(p)}
                    className={`text-left bg-white rounded-lg border border-slate-200 p-4 transition-all group relative cursor-pointer ${
                      isArchived
                        ? "hover:border-amber-400 hover:shadow-sm"
                        : "hover:border-blue-400 hover:shadow-sm"
                    } ${loading ? "opacity-50 pointer-events-none" : ""}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`font-medium truncate group-hover:text-blue-600 ${
                        isArchived ? "text-slate-600" : "text-slate-800"
                      }`}>
                        {p.name || p.source || p.id}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${badge.cls}`}>
                        {badge.text}
                      </span>
                    </div>
                    {p.source && (
                      <p className="text-xs text-slate-400 truncate mb-1" title={p.source}>
                        {p.source}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      <span>{p.total_files} files</span>
                      <span>{p.total_lines.toLocaleString()} lines</span>
                      {formatDate(p.created_at) && <span>{formatDate(p.created_at)}</span>}
                    </div>
                    {isArchived && (
                      <p className="text-xs text-amber-600 mt-2">Click to re-scan and restore</p>
                    )}
                    {/* delete button */}
                    <button
                      onClick={(e) => handleDeleteProject(e, p.id)}
                      className="absolute top-2 right-2 w-6 h-6 rounded-full text-slate-300 hover:text-red-500 hover:bg-red-50 flex items-center justify-center text-sm opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete project"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mt-16">
          {[
            { title: "Wiki Generation", desc: "Project overview, module docs, setup instructions" },
            { title: "Architecture Diagrams", desc: "Auto-detected architecture with Mermaid visuals" },
            { title: "Reading Guide", desc: "PageRank-based file ranking + guided reading path" },
          ].map((f) => (
            <div key={f.title} className="bg-white rounded-lg border border-slate-200 p-5">
              <h3 className="font-semibold text-slate-800 mb-2">{f.title}</h3>
              <p className="text-sm text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="text-center py-4 text-xs text-slate-400">
        <a href="https://github.com/he-yufeng/RepoWiki" className="hover:text-slate-600">
          RepoWiki
        </a>{" "}
        - Open-source DeepWiki alternative
      </footer>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
