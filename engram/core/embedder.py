# engram/core/embedder.py
"""
Single embedding interface for ENGRAM OS.

All embedding calls go through get_embedding().
This is the ONLY place in the codebase that knows
which model is being used.

Model: Ollama all-minilm:l6-v2 (local)
  - 384 dimensions
  - Fast on CPU (~10ms per sentence)
  - Strong semantic performance on code + prose
  - Uses local Ollama model (no HF downloads)

Fallback: hash-based pseudo-embedding
  - Used when Ollama unavailable
  - Same 384 dimensions
  - No semantic meaning — cosine similarities ~0.00
  - Logged as WARNING on first use

To upgrade the model later:
  Change MODEL_NAME constant only.
  All callers automatically use the new model.
"""

import logging
import numpy as np
import urllib.request
import urllib.error
import json
from typing import Optional

# ── Configuration ────────────────────────────────────────────────
MODEL_NAME  = "all-minilm:l6-v2"  # Ollama model name
DIMENSION   = 384
MAX_CHARS   = 8192    # truncate inputs longer than this
OLLAMA_URL  = "http://localhost:11434"


# ── Module-level model cache ────────────────────────────────────
# For Ollama, we just track if it's available
_model_available: bool = False
_model_check_attempted: bool = False
_fallback_used: bool = False


def _check_ollama_available() -> bool:
    """
    Check if Ollama is available and model is loaded.
    Called once on first get_embedding() call.
    Never raises.
    """
    global _model_available, _model_check_attempted

    if _model_check_attempted:
        return _model_available

    _model_check_attempted = True
    try:
        # Check if Ollama is running
        url = f"{OLLAMA_URL}/api/tags"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = data.get('models', [])
            
            # Check if our model is available
            for m in models:
                name = m.get('name', '')
                if MODEL_NAME in name or name.endswith('all-minilm:l6-v2'):
                    _model_available = True
                    logging.info(
                        f"[ENGRAM] embedder: Ollama {MODEL_NAME} available "
                        f"({DIMENSION}-dim)"
                    )
                    return True
            
            # Model not found, try to pull it or use fallback
            logging.warning(
                f"[ENGRAM] embedder: {MODEL_NAME} not found in Ollama. "
                f"Run: ollama pull {MODEL_NAME}"
            )
            _model_available = False
            return False
            
    except Exception as e:
        logging.warning(
            f"[ENGRAM] embedder: Ollama not available at {OLLAMA_URL} — "
            f"using pseudo-embedding fallback. "
            f"Start Ollama: ollama serve"
        )
        _model_available = False
        return False


def get_embedding(text: str) -> np.ndarray:
    """
    Embed a text string into a 384-dimensional vector.

    Uses Ollama all-minilm:l6-v2 when available.
    Falls back to hash-based pseudo-embedding when not.

    Args:
        text: String to embed. Will be truncated at
              MAX_CHARS characters if longer.

    Returns:
        numpy array of shape (384,), dtype float32.
        Never raises. Always returns a valid array.
    """
    global _model_available, _fallback_used

    if not _model_check_attempted:
        _check_ollama_available()

    # Normalise input
    if not text or not isinstance(text, str):
        text = ""
    text = text[:MAX_CHARS].strip()
    if not text:
        text = "[empty]"

    # Ollama embedding
    if _model_available:
        try:
            url = f"{OLLAMA_URL}/api/embeddings"
            payload = {
                "model": MODEL_NAME,
                "prompt": text,
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                embedding = np.array(result.get('embedding', []))
                
                # Normalize to unit vector
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                
                return embedding.astype(np.float32)
                
        except Exception as e:
            if not _fallback_used:
                logging.warning(
                    f"[ENGRAM] embedder: Ollama embed failed: {e} — "
                    f"using fallback"
                )
                _fallback_used = True

    # Pseudo-embedding fallback
    return _pseudo_embedding(text)


def get_embeddings_batch(texts: list) -> np.ndarray:
    """
    Embed a list of strings in one batched call.
    Faster than calling get_embedding() in a loop.

    Args:
        texts: List of strings to embed.

    Returns:
        numpy array of shape (len(texts), 384), float32.
        Rows correspond to input texts in order.
    """
    global _model_available, _fallback_used

    if not _model_check_attempted:
        _check_ollama_available()

    if not texts:
        return np.zeros((0, DIMENSION), dtype=np.float32)

    # Normalise inputs
    cleaned = [
        (t[:MAX_CHARS].strip() if t and isinstance(t, str) else "")
        or "[empty]"
        for t in texts
    ]

    if _model_available:
        try:
            # Ollama doesn't support batch embeddings, embed individually
            embeddings = []
            for text in cleaned:
                url = f"{OLLAMA_URL}/api/embeddings"
                payload = {
                    "model": MODEL_NAME,
                    "prompt": text,
                }
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode())
                    embedding = np.array(result.get('embedding', []))
                    
                    # Normalize
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    
                    embeddings.append(embedding.astype(np.float32))
            
            return np.vstack(embeddings)
            
        except Exception as e:
            if not _fallback_used:
                logging.warning(
                    f"[ENGRAM] embedder: Ollama batch embed failed: {e} — "
                    f"using fallback"
                )
                _fallback_used = True

    # Fallback: embed each individually with pseudo-embedding
    return np.vstack([
        _pseudo_embedding(t) for t in cleaned
    ]).astype(np.float32)


def _pseudo_embedding(text: str) -> np.ndarray:
    """
    Hash-based pseudo-embedding.
    Deterministic but carries no semantic meaning.
    Used ONLY as fallback when Ollama is unavailable.

    Kept here so all embedding logic is in one file.
    """
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng  = np.random.RandomState(seed)
    vec  = rng.randn(DIMENSION).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def using_real_embeddings() -> bool:
    """
    Returns True if Ollama model is available.
    Returns False if using pseudo-embedding fallback.
    Used by router.py to set appropriate thresholds.
    """
    if not _model_check_attempted:
        _check_ollama_available()
    return _model_available


def embedding_info() -> dict:
    """
    Return current embedding configuration.
    Used by `engram doctor` to report embedding status.
    """
    if not _model_check_attempted:
        _check_ollama_available()
    return {
        "model":        MODEL_NAME if using_real_embeddings() else "pseudo",
        "dimension":    DIMENSION,
        "real":         using_real_embeddings(),
        "fallback":     not using_real_embeddings(),
        "source":       "ollama" if using_real_embeddings() else "hash",
    }
