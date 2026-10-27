"""Embedders: text in, unit vectors out.

An embedder is named by a string: ``lexical`` (built in, no network, no install),
``st:<model>`` (sentence-transformers, local), ``voyage:<model>``,
``gemini:<model>`` (Google AI Studio key) or ``vertex:<model>`` (Vertex AI on
Google Cloud). Vectors from two embedders cannot be compared, so the index keeps
one cache per embedder and refuses to mix them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from .kb import KBError
from .vec import Vector, normalize

# -- the built-in lexical embedder -------------------------------------------------

STOP = set("""a an and are as at be been but by can could do does for from had has have he her his how i if in into
is it its just like me more most my no not of on one or our out over she so some such than that the their them
then there these they this those to too up us very was we were what when where which while who will with would
you your also each every any all other only own same both few many much via per about after before between
through during without within i'm i've i'd don't can't it's want need make made using use used get got let
please thing things stuff kind sort way bit really maybe something""".split())

SUFFIXES = ("ations", "ation", "ingly", "ings", "ing", "edly", "ies", "ied", "ers", "er", "ed", "es", "ly", "s")


def _stem(w: str) -> str:
    if len(w) <= 4 or w.isdigit():
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            if suf in ("ies", "ied"):
                base += "y"
            return base
    return w


def _tokens(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return [_stem(w) for w in words if w not in STOP and len(w) > 1]


class LexicalEmbedder:
    """Feature hashing over word stems, word pairs and character 4-grams.

    Deterministic and dependency-free, so the knowledge base always works and
    tests are exact. It matches words, not meanings: two cards that say the same
    thing in different words score low. Cards use the ontology's words, which is
    much of why describing first helps even here; for real use pick a neural
    embedder (``st:``, ``voyage:``, ``gemini:`` or ``vertex:``).
    """

    id = "lexical/1"
    dim = 1024

    def _features(self, text: str) -> Dict[str, float]:
        toks = _tokens(text)
        feats: Dict[str, float] = {}
        for t in toks:
            feats["w:" + t] = feats.get("w:" + t, 0.0) + 1.0
            padded = f"<{t}>"
            if len(padded) > 5:
                grams = [padded[i : i + 4] for i in range(len(padded) - 3)]
                for g in grams:
                    feats["c:" + g] = feats.get("c:" + g, 0.0) + 0.6 / len(grams)
        for a, b in zip(toks, toks[1:]):
            k = "b:" + a + "_" + b
            feats[k] = feats.get(k, 0.0) + 0.5
        return {k: (1.0 + math.log(v)) if v >= 1 else v for k, v in feats.items()}

    def embed(self, texts: List[str], kind: str = "document") -> List[Vector]:
        out = []
        for text in texts:
            v = [0.0] * self.dim
            for feat, weight in self._features(text).items():
                h = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                v[idx] += sign * weight
            out.append(normalize(v))
        return out


# -- sentence-transformers ---------------------------------------------------------

class SentenceTransformerEmbedder:
    def __init__(self, model: str):
        self.model_name = model or "sentence-transformers/all-MiniLM-L6-v2"
        self.id = f"st:{self.model_name}"
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
            except ImportError:
                raise KBError("The st: embedder needs sentence-transformers: pip install sentence-transformers") from None
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: List[str], kind: str = "document") -> List[Vector]:
        model = self._load()
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return [normalize([float(x) for x in v]) for v in vecs]


# -- HTTP embedders -----------------------------------------------------------------

def _post(url: str, body: Dict, headers: Dict[str, str], what: str, tries: int = 4) -> Dict:
    data = json.dumps(body).encode("utf-8")
    delay = 2.0
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise KBError(f"{what} answered {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise KBError(f"Could not reach {what}: {e.reason}") from None
    raise KBError(f"{what} did not answer")


def _env(*names: str) -> Optional[str]:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return None


class VoyageEmbedder:
    """Voyage AI's embedding API (VOYAGE_API_KEY)."""

    def __init__(self, model: str):
        self.model_name = model or "voyage-3.5"
        self.id = f"voyage:{self.model_name}"

    def embed(self, texts: List[str], kind: str = "document") -> List[Vector]:
        key = _env("VOYAGE_API_KEY")
        if not key:
            raise KBError("The voyage: embedder needs VOYAGE_API_KEY")
        out: List[Vector] = []
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            res = _post("https://api.voyageai.com/v1/embeddings",
                        {"input": batch, "model": self.model_name, "input_type": "query" if kind == "query" else "document"},
                        {"Authorization": f"Bearer {key}"}, "Voyage AI")
            rows = sorted(res.get("data", []), key=lambda r: r.get("index", 0))
            out.extend(normalize(r["embedding"]) for r in rows)
        return out


class GeminiEmbedder:
    """Google's Gemini embedding models through the Gemini API (GEMINI_API_KEY or GOOGLE_API_KEY)."""

    def __init__(self, model: str):
        self.model_name = model or "gemini-embedding-001"
        self.id = f"gemini:{self.model_name}"

    def embed(self, texts: List[str], kind: str = "document") -> List[Vector]:
        key = _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if not key:
            raise KBError("The gemini: embedder needs GEMINI_API_KEY (or GOOGLE_API_KEY)")
        task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:batchEmbedContents"
        out: List[Vector] = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            body = {"requests": [{"model": f"models/{self.model_name}", "content": {"parts": [{"text": t}]}, "taskType": task} for t in batch]}
            res = _post(url, body, {"x-goog-api-key": key}, "the Gemini API")
            out.extend(normalize(e["values"]) for e in res.get("embeddings", []))
        return out


class VertexEmbedder:
    """Google's embedding models on Vertex AI, billed to a Google Cloud project.

    Needs GOOGLE_CLOUD_PROJECT (and optionally GOOGLE_CLOUD_LOCATION, default
    us-central1) and a token: GOOGLE_OAUTH_ACCESS_TOKEN, or `gcloud auth
    print-access-token` on the PATH.
    """

    def __init__(self, model: str):
        self.model_name = model or "gemini-embedding-001"
        self.id = f"vertex:{self.model_name}"

    def _token(self) -> str:
        tok = _env("GOOGLE_OAUTH_ACCESS_TOKEN")
        if tok:
            return tok
        gcloud = shutil.which("gcloud")
        if not gcloud:
            raise KBError("The vertex: embedder needs GOOGLE_OAUTH_ACCESS_TOKEN or the gcloud command (gcloud auth login)")
        res = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True)
        if res.returncode != 0:
            raise KBError("gcloud could not print an access token: " + res.stderr.strip()[:300])
        return res.stdout.strip()

    def embed(self, texts: List[str], kind: str = "document") -> List[Vector]:
        project = _env("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT")
        if not project:
            raise KBError("The vertex: embedder needs GOOGLE_CLOUD_PROJECT")
        loc = _env("GOOGLE_CLOUD_LOCATION") or "us-central1"
        url = (f"https://{loc}-aiplatform.googleapis.com/v1/projects/{project}/locations/{loc}"
               f"/publishers/google/models/{self.model_name}:predict")
        headers = {"Authorization": f"Bearer {self._token()}"}
        task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
        # gemini-embedding-001 takes one text per request on Vertex; the older models take batches.
        step = 1 if "gemini" in self.model_name else 16
        out: List[Vector] = []
        for i in range(0, len(texts), step):
            batch = texts[i : i + step]
            res = _post(url, {"instances": [{"content": t, "task_type": task} for t in batch]}, headers, "Vertex AI")
            out.extend(normalize(p["embeddings"]["values"]) for p in res.get("predictions", []))
        return out


def get_embedder(name: Optional[str]):
    name = (name or "lexical").strip()
    if name in ("lexical", "lexical/1"):
        return LexicalEmbedder()
    provider, _, model = name.partition(":")
    if provider in ("st", "sentence-transformers"):
        return SentenceTransformerEmbedder(model)
    if provider == "voyage":
        return VoyageEmbedder(model)
    if provider == "gemini":
        return GeminiEmbedder(model)
    if provider == "vertex":
        return VertexEmbedder(model)
    raise KBError(f"Unknown embedder {name!r}: use lexical, st:<model>, voyage:<model>, gemini:<model> or vertex:<model>")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
