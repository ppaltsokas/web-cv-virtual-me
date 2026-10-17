"""Manifest-only document access and owner-bound lexical/semantic retrieval."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from .profile import Profile, Manifest, DocumentSpec, document_path
from .cost_controls import require_paid_ai

@dataclass(frozen=True)
class Chunk:
    source: str
    label: str
    text: str

def extract_text(path: Path) -> str:
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported')
        if len(reader.pages) > 400:
            raise ValueError('PDF exceeds the 400-page limit')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    else:
        text = path.read_text(encoding='utf-8-sig')
    if not text.strip():
        raise ValueError('Document has no extractable text. Supply a text-based PDF or an OCR transcript.')
    if len(text) > 600_000:
        raise ValueError('Document exceeds the 600,000-character text limit')
    return text

def tokens(text: str) -> set[str]:
    return set(re.findall(r'\w{2,}', text.casefold(), re.UNICODE))

class KnowledgeBase:
    def __init__(self, profile: Profile, manifest: Manifest, root: Path, index_dir: Path | None = None):
        self.profile, self.manifest, self.root = profile, manifest, root
        self.documents: dict[str, tuple[DocumentSpec, Path]] = {}
        profile_text = profile.evidence()
        self.chunks = [Chunk('profile', 'Portfolio profile', profile_text[start:start + 2000]) for start in range(0, len(profile_text), 1600)]
        digest = hashlib.sha256(profile.model_dump_json().encode())
        digest.update(manifest.model_dump_json().encode())
        total = 0
        for spec in manifest.documents:
            path = document_path(root, spec)
            data = path.read_bytes()
            digest.update(hashlib.sha256(data).digest())
            text = extract_text(path)
            total += len(text)
            if total > 3_000_000:
                raise ValueError('Combined document text exceeds 3 million characters')
            self.documents[spec.id] = (spec, path)
            for start in range(0, len(text), 1600):
                self.chunks.append(Chunk(spec.id, spec.label, text[start:start + 2000]))
        self.fingerprint = digest.hexdigest()
        self.index, self.index_chunks = None, None
        self.model = os.getenv('EMBEDDINGS_MODEL', 'text-embedding-3-small')
        if index_dir is not None:
            self._load_index(index_dir)

    def _load_index(self, directory: Path):
        metadata = directory / 'store.json'
        binary = directory / 'index.faiss'
        if not metadata.is_file() or not binary.is_file():
            return
        try:
            store = json.loads(metadata.read_text(encoding='utf-8'))
            if store['fingerprint'] != self.fingerprint or store['embedding_model'] != self.model:
                return  # An old owner's index must never become this owner's evidence.
            if hashlib.sha256(binary.read_bytes()).hexdigest() != store['index_sha256']:
                return
            import faiss
            index = faiss.read_index(str(binary))
            expected = [chunk.__dict__ for chunk in self.chunks]
            if store['chunks'] != expected or index.ntotal != len(expected):
                return
            self.index, self.index_chunks = index, self.chunks
        except (ValueError, KeyError, OSError, RuntimeError):
            self.index, self.index_chunks = None, None

    def catalog(self) -> str:
        return '\n'.join(f'{spec.id}: {spec.label}' for spec in self.manifest.documents)

    def search(self, query: str, client=None, limit: int = 5) -> list[Chunk]:
        terms = tokens(query)
        scores = []
        for i, chunk in enumerate(self.chunks):
            content = tokens(chunk.label + ' ' + chunk.text)
            label_matches = len(terms & tokens(chunk.label))
            score = len(terms & content) / math.sqrt(max(1, len(content))) + label_matches
            if score > 0:
                scores.append((score, i))
        ranked = [i for _, i in sorted(scores, reverse=True)[:limit]]
        if self.index is not None and client is not None:
            require_paid_ai()
            import numpy as np
            import faiss
            result = client.with_options(timeout=20.0, max_retries=0).embeddings.create(model=self.model, input=[query[:4000]])
            vector = np.asarray([result.data[0].embedding], dtype='float32')
            faiss.normalize_L2(vector)
            _, indices = self.index.search(vector, min(limit, self.index.ntotal))
            ranked = list(dict.fromkeys(list(map(int, indices[0])) + ranked))[:limit]
        return [self.chunks[i] for i in ranked if i >= 0]

    def build_index(self, directory: Path, client) -> int:
        require_paid_ai()
        import faiss
        import numpy as np
        vectors = []
        for start in range(0, len(self.chunks), 32):
            require_paid_ai()
            response = client.with_options(timeout=45.0, max_retries=0).embeddings.create(
                model=self.model, input=[chunk.text for chunk in self.chunks[start:start + 32]])
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        matrix = np.asarray(vectors, dtype='float32')
        if len(matrix) != len(self.chunks) or not np.isfinite(matrix).all():
            raise ValueError('Invalid embedding response')
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / 'index.faiss.new'
        faiss.write_index(index, str(temporary))
        store = {'fingerprint': self.fingerprint, 'embedding_model': self.model,
                 'index_sha256': hashlib.sha256(temporary.read_bytes()).hexdigest(),
                 'chunks': [chunk.__dict__ for chunk in self.chunks]}
        metadata = directory / 'store.json.new'
        metadata.write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
        temporary.replace(directory / 'index.faiss')
        metadata.replace(directory / 'store.json')
        return len(self.chunks)
