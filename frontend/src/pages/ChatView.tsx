import { useState, useRef, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { streamChat, deepDive } from "../lib/api";
import { useWikiStore } from "../stores/wiki";

interface DeepDiveSuggestion {
  keywords: string[];
  question: string;
}

export default function ChatView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { chatMessages, addChatMessage, appendToLastChat, setLastChatReferences, settings } = useWikiStore();
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [deepDiveSuggestions, setDeepDiveSuggestions] = useState<Record<number, DeepDiveSuggestion>>({});
  const [deepDiving, setDeepDiving] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, deepDiveSuggestions]);

  function handleSend() {
    if (!input.trim() || !id || streaming) return;
    const question = input.trim();
    setInput("");
    addChatMessage({ role: "user", content: question });
    addChatMessage({ role: "assistant", content: "" });
    setStreaming(true);

    const msgIndex = chatMessages.length + 1; // index of the assistant message

    streamChat(
      id,
      question,
      (data) => {
        if (data.references) setLastChatReferences(data.references);
        if (data.error) {
          const modelInfo = data.model ? `\n\nModel: ${data.model}` : "";
          const baseInfo = data.api_base ? `\nBase URL: ${data.api_base}` : "";
          appendToLastChat(`⚠️ ${data.error}${modelInfo}${baseInfo}\n\nPlease check your API Key and Base URL in Settings, then try again.`);
        }
        if (data.deep_dive_suggestion) {
          setDeepDiveSuggestions((prev) => ({ ...prev, [msgIndex]: data.deep_dive_suggestion }));
        }
        if (data.content) appendToLastChat(data.content);
      },
      () => setStreaming(false),
      {
        model: settings.model || undefined,
        api_base: settings.apiBase || undefined,
      },
    );
  }

  async function handleDeepDive(msgIndex: number, suggestion: DeepDiveSuggestion) {
    if (!id) return;
    setDeepDiving(msgIndex);
    try {
      const result = await deepDive(id, suggestion.question, suggestion.keywords, {
        model: settings.model || undefined,
        api_base: settings.apiBase || undefined,
      });
      if (result.error) {
        addChatMessage({ role: "assistant", content: `⚠️ 深度分析失败：${result.error}` });
      } else {
        addChatMessage({
          role: "assistant",
          content: `🔍 **深度分析完成**\n\n${result.analysis}\n\n---\n*已生成 wiki 页面：${result.page_id}*`,
          references: result.references.map((r) => ({
            path: r.path,
            line_start: r.line_start,
            line_end: r.line_end,
            snippet: "",
          })),
        });
      }
      // clear the suggestion (user acted on it)
      setDeepDiveSuggestions((prev) => {
        const next = { ...prev };
        delete next[msgIndex];
        return next;
      });
    } catch (e: any) {
      addChatMessage({ role: "assistant", content: `⚠️ 深度分析出错：${e.message}` });
    } finally {
      setDeepDiving(null);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      {/* header */}
      <header className="flex items-center gap-4 px-6 py-3 bg-white border-b border-slate-200">
        <button
          onClick={() => navigate(`/project/${id}`)}
          className="text-slate-500 hover:text-slate-700"
        >
          &larr; Back to Wiki
        </button>
        <h1 className="text-lg font-semibold text-slate-800">Ask about this codebase</h1>
      </header>

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {chatMessages.length === 0 && (
          <div className="text-center text-slate-400 mt-20">
            <p className="text-lg mb-2">Ask anything about the codebase</p>
            <p className="text-sm">e.g. "How does the authentication flow work?"</p>
          </div>
        )}
        {chatMessages.map((msg, i) => (
          <div
            key={i}
            className={`max-w-2xl ${msg.role === "user" ? "ml-auto" : "mr-auto"}`}
          >
            <div
              className={`rounded-lg px-4 py-3 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-slate-200 text-slate-700"
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans text-sm">{msg.content}</pre>
              {msg.references && msg.references.length > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-100 space-y-2">
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Sources</p>
                  {msg.references.map((ref, j) => (
                    <details key={j} className="group rounded border border-slate-200 bg-slate-50">
                      <summary className="cursor-pointer select-none px-3 py-1.5 text-xs font-mono text-blue-700 hover:bg-slate-100 rounded">
                        {ref.path}:{ref.line_start}-{ref.line_end}
                      </summary>
                      <pre className="px-3 py-2 text-xs font-mono text-slate-600 whitespace-pre-wrap border-t border-slate-200">{ref.snippet}</pre>
                    </details>
                  ))}
                </div>
              )}
            </div>
            {/* deep-dive suggestion */}
            {msg.role === "assistant" && deepDiveSuggestions[i] && (
              <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-4">
                <p className="text-sm text-amber-800 font-medium mb-2">
                  💡 检测到深度分析需求
                </p>
                <p className="text-xs text-amber-700 mb-3">
                  建议使用扩展关键词重新检索代码，生成深入的专题分析并保存为 wiki 页面。
                  <br />
                  推荐关键词：{deepDiveSuggestions[i].keywords.map((k, j) => (
                    <span key={j} className="inline-block bg-amber-200 text-amber-800 px-2 py-0.5 rounded text-xs mr-1 mb-1 font-mono">{k}</span>
                  ))}
                </p>
                <button
                  onClick={() => handleDeepDive(i, deepDiveSuggestions[i])}
                  disabled={deepDiving !== null}
                  className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {deepDiving === i ? "🔍 正在深度分析..." : "🔍 开始深度分析"}
                </button>
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* input */}
      <div className="px-6 py-4 bg-white border-t border-slate-200">
        <div className="max-w-2xl mx-auto flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask a question..."
            className="flex-1 px-4 py-2.5 rounded-lg border border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none text-sm"
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
