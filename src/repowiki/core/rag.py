"""lightweight TF-IDF retrieval for Q&A chat."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from repowiki.core.models import ProjectContext


@dataclass
class Chunk:
    file_path: str
    line_start: int
    line_end: int
    content: str
    score: float = 0.0


class SimpleRAG:
    """TF-IDF based code retrieval, no external dependencies."""

    def __init__(self):
        self.chunks: list[Chunk] = []
        self._idf: dict[str, float] = {}
        self._tf_vectors: list[Counter] = []

    def index(self, project: ProjectContext) -> None:
        """chunk project files and build the TF-IDF index."""
        self.chunks = []
        for f in project.files:
            text = f.content or f.preview
            if not text:
                continue
            file_chunks = _split_into_chunks(text, f.path)
            self.chunks.extend(file_chunks)

        # build IDF
        doc_count = len(self.chunks)
        if doc_count == 0:
            return

        df: Counter = Counter()
        self._tf_vectors = []

        for chunk in self.chunks:
            tokens = _tokenize(chunk.content)
            tf = Counter(tokens)
            self._tf_vectors.append(tf)
            for token in set(tokens):
                df[token] += 1

        self._idf = {token: math.log(doc_count / (count + 1)) for token, count in df.items()}

    def retrieve(self, query: str, top_k: int = 5) -> list[Chunk]:
        """find top-k chunks most relevant to the query."""
        if not self.chunks:
            return []

        query_tokens = _tokenize(query)
        query_tf = Counter(query_tokens)

        scores = []
        for i, chunk in enumerate(self.chunks):
            tf_vec = self._tf_vectors[i]
            score = _cosine_similarity(query_tf, tf_vec, self._idf)
            scores.append((score, i))

        scores.sort(reverse=True)
        results = []
        for score, idx in scores[:top_k]:
            if score <= 0:
                break
            chunk = self.chunks[idx]
            chunk.score = score
            results.append(chunk)

        return results


def format_context(chunks: list[Chunk]) -> str:
    """Render retrieved chunks into a prompt-ready context block.

    Each chunk becomes a fenced section labelled with its file path and line
    range, so the model can cite specific locations. Empty input yields a
    short placeholder rather than a blank prompt.
    """
    if not chunks:
        return "(no relevant code found in this repository)"
    blocks = []
    for c in chunks:
        blocks.append(
            f"### {c.file_path} (lines {c.line_start}-{c.line_end})\n```\n{c.content}\n```"
        )
    return "\n\n".join(blocks)


def _tokenize(text: str) -> list[str]:
    """split text into lowercase tokens, keeping identifiers intact.

    Handles ASCII identifiers (snake_case, camelCase) and CJK text (Chinese,
    Japanese, Korean). CJK characters are tokenized into runs so that Chinese
    comments and queries are searchable -- without this, a query like
    '核心业务' produces zero tokens and retrieves nothing.
    """
    text = text.lower()
    # ASCII identifiers: letters, digits, underscore ( Programming identifiers)
    ascii_tokens = re.findall(r"[a-z_]\w*", text)
    # CJK runs: Chinese, Japanese (hiragana/katakana), Korean, CJK punctuation
    # Split on whitespace/punctuation within CJK so we get meaningful units
    # rather than one giant blob. Use 1+ char runs for short phrases.
    cjk_runs = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", text)
    # further split CJK runs into 2-char bigrams for better matching
    # (single chars are too generic, full runs are too specific)
    cjk_tokens = []
    for run in cjk_runs:
        if len(run) <= 2:
            cjk_tokens.append(run)
        else:
            for i in range(len(run) - 1):
                cjk_tokens.append(run[i:i + 2])
    return ascii_tokens + cjk_tokens


def _cosine_similarity(vec_a: Counter, vec_b: Counter, idf: dict[str, float]) -> float:
    """TF-IDF weighted cosine similarity."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0

    dot = sum(vec_a[t] * idf.get(t, 0) * vec_b[t] * idf.get(t, 0) for t in common)
    norm_a = math.sqrt(sum((vec_a[t] * idf.get(t, 0)) ** 2 for t in vec_a))
    norm_b = math.sqrt(sum((vec_b[t] * idf.get(t, 0)) ** 2 for t in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _split_into_chunks(text: str, file_path: str, max_chunk_lines: int = 30) -> list[Chunk]:
    """split file content into chunks at blank line boundaries."""
    lines = text.splitlines()
    chunks = []
    current_start = 0
    current_lines: list[str] = []

    for i, line in enumerate(lines):
        current_lines.append(line)

        # split at blank lines or when chunk gets too large
        is_boundary = line.strip() == "" and len(current_lines) >= 5
        is_too_long = len(current_lines) >= max_chunk_lines

        if is_boundary or is_too_long or i == len(lines) - 1:
            if current_lines:
                content = "\n".join(current_lines)
                if content.strip():
                    chunks.append(
                        Chunk(
                            file_path=file_path,
                            line_start=current_start + 1,
                            line_end=current_start + len(current_lines),
                            content=content,
                        )
                    )
                current_start = i + 1
                current_lines = []

    return chunks
