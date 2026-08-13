import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getWiki, getPage, reanalyzeProject, deleteProject, getProjectInfo } from "../lib/api";
import { useWikiStore } from "../stores/wiki";
import WikiSidebar from "../components/WikiSidebar";
import WikiContent from "../components/WikiContent";

export default function WikiView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { wiki, setWiki, currentPageId, setCurrentPage, reset } = useWikiStore();
  const [pageContent, setPageContent] = useState("");
  const [pageTitle, setPageTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeMsg, setReanalyzeMsg] = useState("");
  const timerRef = useRef<number | undefined>(undefined);

  // load wiki structure if not already loaded
  useEffect(() => {
    if (!wiki && id) {
      getWiki(id).then((w) => {
        if ("error" in w) {
          navigate("/");
          return;
        }
        setWiki(w);
      });
    }
  }, [id, wiki]);

  // load page content when currentPageId changes
  useEffect(() => {
    if (!id || !currentPageId) return;
    setLoading(true);
    getPage(id, currentPageId).then((p) => {
      if ("error" in p) {
        setPageContent("Page not found");
        setPageTitle("Error");
      } else {
        setPageContent(p.content);
        setPageTitle(p.title);
      }
      setLoading(false);
    });
  }, [id, currentPageId]);

  if (!wiki) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Loading wiki...
      </div>
    );
  }

  async function handleReanalyze() {
    if (!id || reanalyzing) return;
    setReanalyzing(true);
    setReanalyzeMsg("Starting re-analysis...");
    try {
      await reanalyzeProject(id);
      // poll status until done/error — more reliable than SSE for short tasks
      const poll = async () => {
        try {
          const info = await getProjectInfo(id);
          if (info.status === "done") {
            const fresh = await getWiki(id);
            setWiki(fresh);
            setReanalyzing(false);
            setReanalyzeMsg("");
            setCurrentPage(currentPageId);  // reload page content
            return;
          }
          if (info.status === "error") {
            setReanalyzing(false);
            setReanalyzeMsg("Re-analysis failed: " + (info.error || "unknown error"));
            return;
          }
          // still running — show a status message and keep polling
          setReanalyzeMsg(`Re-analyzing... (${info.status})`);
          timerRef.current = window.setTimeout(poll, 1500);
        } catch {
          setReanalyzing(false);
          setReanalyzeMsg("Lost connection to server");
        }
      };
      timerRef.current = window.setTimeout(poll, 1000);
    } catch (e: any) {
      setReanalyzing(false);
      setReanalyzeMsg("Error: " + e.message);
    }
  }

  async function handleDelete() {
    if (!id) return;
    if (!confirm(`Delete this project? This removes it from the list. (Files on disk are not touched.)`)) return;
    await deleteProject(id);
    reset();
    navigate("/");
  }

  return (
    <div className="flex h-screen bg-white">
      {/* sidebar */}
      <WikiSidebar
        sidebar={wiki.sidebar}
        currentPageId={currentPageId}
        projectName={wiki.project_name}
        onNavigate={(pageId) => setCurrentPage(pageId)}
        onChat={() => navigate(`/project/${id}/chat`)}
        onHome={() => navigate("/")}
        onReanalyze={handleReanalyze}
        onDelete={handleDelete}
      />

      {/* main content */}
      <div className="flex-1 overflow-y-auto">
        {reanalyzing && (
          <div className="sticky top-0 z-10 bg-blue-50 border-b border-blue-200 px-8 py-3 text-sm text-blue-700 flex items-center gap-2">
            <span className="animate-pulse">⟳</span>
            {reanalyzeMsg || "Re-analyzing..."}
          </div>
        )}
        {loading ? (
          <div className="p-12 text-slate-400 animate-pulse">Loading page...</div>
        ) : (
          <WikiContent content={pageContent} title={pageTitle} />
        )}
      </div>
    </div>
  );
}
