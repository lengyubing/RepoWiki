import { useEffect, useState } from "react";
import { useWikiStore } from "../stores/wiki";
import {
  getPrompts,
  savePrompts,
  resetPrompts,
  type PromptTemplates,
} from "../lib/api";

interface Props {
  onClose: () => void;
}

const PROMPT_LABELS: Record<string, string> = {
  overview: "Project Overview",
  module: "Module Docs",
  architecture: "Architecture",
  reading_guide: "Reading Guide",
  chat: "Chat / Q&A",
};

const PROMPT_VARS: Record<string, string> = {
  overview: "{file_tree}  {key_files}",
  module: "{module_name}  {files_context}  {project_summary}",
  architecture: "{file_tree}  {key_files}",
  reading_guide: "{rankings}  {module_summaries}",
  chat: "{question}  {context_chunks}",
};

export default function SettingsModal({ onClose }: Props) {
  const { settings, updateSettings } = useWikiStore();
  const [tab, setTab] = useState<"model" | "prompts">("model");

  // prompt editor state
  const [prompts, setPrompts] = useState<PromptTemplates>({});
  const [defaults, setDefaults] = useState<PromptTemplates>({});
  const [activePrompt, setActivePrompt] = useState<string>("overview");
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    if (tab === "prompts" && Object.keys(prompts).length === 0) {
      getPrompts().then((data) => {
        setPrompts(data.current);
        setDefaults(data.defaults);
      });
    }
  }, [tab, prompts]);

  function onPromptChange(role: "system" | "user", value: string) {
    setPrompts((prev) => ({
      ...prev,
      [activePrompt]: { ...prev[activePrompt], [role]: value },
    }));
    setDirty((prev) => ({ ...prev, [activePrompt]: true }));
    setSaveMsg("");
  }

  async function handleSave() {
    setSaving(true);
    try {
      const data = await savePrompts(prompts);
      setPrompts(data.current);
      setDirty({});
      setSaveMsg("Saved! Changes apply to the next scan.");
    } catch {
      setSaveMsg("Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    try {
      const data = await resetPrompts();
      setPrompts(data.current);
      setDefaults(data.defaults);
      setDirty({});
      setSaveMsg("Reset to defaults.");
    } catch {
      setSaveMsg("Reset failed.");
    } finally {
      setSaving(false);
    }
  }

  function resetOne(key: string) {
    setPrompts((prev) => ({
      ...prev,
      [key]: { ...defaults[key] },
    }));
    setDirty((prev) => ({ ...prev, [key]: true }));
    setSaveMsg("");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header + tabs */}
        <div className="border-b border-slate-200 px-6 pt-5">
          <div className="flex gap-4">
            <button
              onClick={() => setTab("model")}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                tab === "model"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              Model Settings
            </button>
            <button
              onClick={() => setTab("prompts")}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                tab === "prompts"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              Prompt Templates
            </button>
          </div>
        </div>

        {/* body */}
        <div className="px-6 py-5 overflow-y-auto flex-1">
          {tab === "model" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">API Key</label>
                <input
                  type="password"
                  value={settings.apiKey}
                  onChange={(e) => {
                    updateSettings({ apiKey: e.target.value });
                    localStorage.setItem("repowiki_api_key", e.target.value);
                  }}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none"
                />
                <p className="text-xs text-slate-400 mt-1">DeepSeek, OpenAI, or Anthropic API key</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Base URL</label>
                <input
                  type="text"
                  value={settings.apiBase}
                  onChange={(e) => updateSettings({ apiBase: e.target.value })}
                  placeholder="https://api.openai.com/v1 (optional)"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none"
                />
                <p className="text-xs text-slate-400 mt-1">
                  Optional. Override the LLM endpoint, e.g. an OpenAI-compatible proxy or a
                  self-hosted gateway. Leave blank to use the provider default.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Model</label>
                <select
                  value={settings.model}
                  onChange={(e) => updateSettings({ model: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-blue-500 outline-none"
                >
                  <option value="deepseek">DeepSeek V3.2</option>
                  <option value="opus">Claude Opus 4.6</option>
                  <option value="claude">Claude Sonnet 4.6</option>
                  <option value="gpt">GPT-5.4</option>
                  <option value="gpt-mini">GPT-5.4 Mini</option>
                  <option value="gemini">Gemini 3.1 Pro</option>
                  <option value="gemini-flash">Gemini 2.5 Flash</option>
                  <option value="qwen">Qwen3.5 Plus</option>
                  <option value="kimi">Kimi K2.6</option>
                  <option value="glm">GLM-5</option>
                  <option value="minimax">MiniMax M2.7</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Language</label>
                <select
                  value={settings.language}
                  onChange={(e) => updateSettings({ language: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-blue-500 outline-none"
                >
                  <option value="en">English</option>
                  <option value="zh">中文</option>
                  <option value="ja">日本語</option>
                  <option value="ko">한국어</option>
                </select>
              </div>
            </div>
          )}

          {tab === "prompts" && (
            <div className="flex gap-4 min-h-[360px]">
              {/* prompt list */}
              <div className="w-44 shrink-0 space-y-1">
                {Object.keys(prompts).length === 0 && (
                  <p className="text-xs text-slate-400">Loading...</p>
                )}
                {Object.keys(prompts).map((key) => (
                  <button
                    key={key}
                    onClick={() => {
                      setActivePrompt(key);
                      setSaveMsg("");
                    }}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                      activePrompt === key
                        ? "bg-blue-50 text-blue-700 font-medium"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {PROMPT_LABELS[key] || key}
                    {dirty[key] && <span className="ml-1 text-orange-500">*</span>}
                  </button>
                ))}
              </div>

              {/* editor */}
              <div className="flex-1 min-w-0 space-y-3">
                {prompts[activePrompt] && (
                  <>
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-slate-400">
                        Variables: <code className="text-slate-500">{PROMPT_VARS[activePrompt]}</code>
                      </p>
                      <button
                        onClick={() => resetOne(activePrompt)}
                        className="text-xs text-slate-400 hover:text-slate-600"
                      >
                        Reset this one
                      </button>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">
                        System Prompt
                      </label>
                      <textarea
                        value={prompts[activePrompt].system}
                        onChange={(e) => onPromptChange("system", e.target.value)}
                        rows={4}
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs font-mono focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none resize-y"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">
                        User Prompt
                      </label>
                      <textarea
                        value={prompts[activePrompt].user}
                        onChange={(e) => onPromptChange("user", e.target.value)}
                        rows={10}
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs font-mono focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none resize-y"
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* footer */}
        <div className="border-t border-slate-200 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {tab === "prompts" && (
              <>
                <span className="text-xs text-slate-400">{saveMsg}</span>
                {Object.keys(prompts).length > 0 && (
                  <button
                    onClick={handleReset}
                    disabled={saving}
                    className="text-xs text-slate-500 hover:text-red-600 disabled:opacity-50"
                  >
                    Reset all to defaults
                  </button>
                )}
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            {tab === "prompts" && (
              <button
                onClick={handleSave}
                disabled={saving || Object.keys(dirty).length === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? "Saving..." : "Save Prompts"}
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-100 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
