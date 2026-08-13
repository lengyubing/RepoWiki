const BASE = "/api";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = localStorage.getItem("repowiki_api_key");
  if (apiKey) headers["x-api-key"] = apiKey;
  return headers;
}

export interface ScanRequest {
  path?: string;
  url?: string;
  language?: string;
  model?: string;
  api_base?: string;
  supplementary_docs?: string;
  custom_instructions?: string;
}

export interface ProjectInfo {
  id: string;
  name: string;
  status: string;
  total_files: number;
  total_lines: number;
  error?: string;
  source?: string;
  created_at?: number;
}

export interface WikiStructure {
  project_name: string;
  sidebar: SidebarItem[];
  pages: PageMeta[];
}

export interface SidebarItem {
  title: string;
  page_id: string;
  children?: SidebarItem[];
}

export interface PageMeta {
  id: string;
  title: string;
  order: number;
  parent_id: string;
}

export interface WikiPage {
  id: string;
  title: string;
  content: string;
}

export async function scanProject(req: ScanRequest): Promise<ProjectInfo> {
  const res = await fetch(`${BASE}/scan`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(req),
  });
  return res.json();
}

export async function listProjects(): Promise<ProjectInfo[]> {
  const res = await fetch(`${BASE}/projects`, { headers: getHeaders() });
  const data = await res.json();
  return data.projects || [];
}

export async function deleteProject(projectId: string): Promise<void> {
  await fetch(`${BASE}/projects/${projectId}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
}

export async function reanalyzeProject(projectId: string): Promise<ProjectInfo> {
  const res = await fetch(`${BASE}/project/${projectId}/reanalyze`, {
    method: "POST",
    headers: getHeaders(),
  });
  return res.json();
}

export interface PromptTemplates {
  [key: string]: { system: string; user: string };
}

export interface PromptsResponse {
  current: PromptTemplates;
  defaults: PromptTemplates;
  keys: string[];
}

export async function getPrompts(): Promise<PromptsResponse> {
  const res = await fetch(`${BASE}/prompts`, { headers: getHeaders() });
  return res.json();
}

export async function savePrompts(prompts: PromptTemplates): Promise<PromptsResponse> {
  const res = await fetch(`${BASE}/prompts`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({ prompts }),
  });
  return res.json();
}

export async function resetPrompts(): Promise<PromptsResponse> {
  const res = await fetch(`${BASE}/prompts/reset`, {
    method: "POST",
    headers: getHeaders(),
  });
  return res.json();
}

export function streamScanProgress(
  projectId: string,
  onProgress: (step: string) => void,
  onDone: (status: string) => void,
) {
  const es = new EventSource(`${BASE}/project/${projectId}/status`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.step) onProgress(data.step);
    if (data.status) {
      onDone(data.status);
      es.close();
    }
    if (data.error) {
      onDone("error");
      es.close();
    }
  };
  es.onerror = () => {
    es.close();
    onDone("error");
  };
  return es;
}

export async function getWiki(projectId: string): Promise<WikiStructure> {
  const res = await fetch(`${BASE}/project/${projectId}/wiki`, { headers: getHeaders() });
  return res.json();
}

export async function getProjectInfo(projectId: string): Promise<ProjectInfo> {
  const res = await fetch(`${BASE}/project/${projectId}`, { headers: getHeaders() });
  return res.json();
}

export async function getPage(projectId: string, pageId: string): Promise<WikiPage> {
  const res = await fetch(`${BASE}/project/${projectId}/wiki/${pageId}`, { headers: getHeaders() });
  return res.json();
}

export async function getFileContent(projectId: string, filePath: string) {
  const res = await fetch(`${BASE}/project/${projectId}/file/${filePath}`, { headers: getHeaders() });
  return res.json();
}

export function streamChat(
  projectId: string,
  question: string,
  onChunk: (data: any) => void,
  onDone: () => void,
  opts?: { model?: string; api_base?: string },
) {
  const body: Record<string, unknown> = { question };
  if (opts?.model) body.model = opts.model;
  if (opts?.api_base) body.api_base = opts.api_base;
  fetch(`${BASE}/project/${projectId}/chat`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  }).then(async (res) => {
    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    if (!reader) return;

    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            onChunk(data);
            if (data.done) onDone();
          } catch {}
        }
      }
    }
    onDone();
  });
}

export interface ChatError {
  error: string;
  model?: string;
  api_base?: string;
}

export interface DeepDiveResponse {
  analysis: string;
  references: { path: string; line_start: number; line_end: number }[];
  page_id: string;
  error?: string;
}

export async function deepDive(
  projectId: string,
  question: string,
  keywords: string[],
  opts?: { model?: string; api_base?: string },
): Promise<DeepDiveResponse> {
  const res = await fetch(`${BASE}/project/${projectId}/deep-dive`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ question, keywords, ...opts }),
  });
  return res.json();
}
