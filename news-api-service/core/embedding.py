# -*- coding: utf-8 -*-
"""文本向量化模块

支持多种 Embedding 后端：
  1. 智谱 embedding-3 API（推荐，中文效果好）
  2. sentence-transformers 本地模型（如 BAAI/bge-small-zh-v1.5）
  3. 简易哈希向量（仅测试用，无语义能力）

自动检测可用后端，优雅降级。
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_config
from core.logger import get_logger

logger = get_logger("embedding")


class EmbeddingClient:
    """统一向量化客户端"""

    def __init__(
        self,
        backend: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        cfg = get_config()
        self._backend = backend or cfg.embedding_backend
        self._model_name = model_name or cfg.embedding_model
        self._dim = cfg.embedding_dim
        self._api_key = cfg.zhipu_api_key or cfg.zai_api_key
        self._local_model: Any = None

        if self._backend == "zhipu" and not self._api_key:
            logger.warning("智谱 API Key 未配置，降级为 hash 向量")
            self._backend = "hash"

        if self._backend == "local":
            self._init_local_model()

        logger.info(
            "Embedding 初始化 | backend=%s model=%s dim=%d",
            self._backend, self._model_name, self._dim,
        )

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> List[float]:
        """单文本向量化"""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if not texts:
            return []

        if self._backend == "zhipu":
            return self._embed_zhipu(texts)
        elif self._backend == "local":
            return self._embed_local(texts)
        else:
            return self._embed_hash(texts)

    # ── 智谱 embedding API ──

    def _embed_zhipu(self, texts: List[str]) -> List[List[float]]:
        url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        all_vectors: List[List[float]] = []
        batch_size = 16  # 智谱 API 单批上限

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch = [t[:8000] if t else " " for t in batch]
            payload: Dict[str, Any] = {
                "model": self._model_name,
                "input": batch,
            }
            if self._dim:
                payload["dimensions"] = self._dim

            for attempt in range(3):
                try:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    embeddings = sorted(data["data"], key=lambda x: x["index"])
                    for item in embeddings:
                        vec = item["embedding"]
                        if self._dim and len(vec) != self._dim:
                            self._dim = len(vec)
                        all_vectors.append(vec)
                    break
                except Exception as e:
                    logger.warning(
                        "智谱 embedding 失败 attempt=%d: %s", attempt + 1, e
                    )
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        logger.error("智谱 embedding 彻底失败，降级 hash")
                        all_vectors.extend(self._embed_hash(batch))

        return all_vectors

    # ── 本地 sentence-transformers ──

    def _init_local_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self._model_name)
            test = self._local_model.encode(["测试"])
            self._dim = len(test[0])
            logger.info(
                "本地 Embedding 模型加载成功 | model=%s dim=%d",
                self._model_name, self._dim,
            )
        except ImportError:
            logger.warning(
                "sentence-transformers 未安装，降级为 hash 向量"
            )
            self._backend = "hash"
        except Exception as e:
            logger.warning("本地模型加载失败: %s，降级 hash", e)
            self._backend = "hash"

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        if self._local_model is None:
            return self._embed_hash(texts)
        vecs = self._local_model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    # ── Hash 降级（仅测试） ──

    def _embed_hash(self, texts: List[str]) -> List[List[float]]:
        return [self._text_to_hash_vector(t) for t in texts]

    def _text_to_hash_vector(self, text: str) -> List[float]:
        """将文本哈希映射为固定维度的伪向量（无语义能力，仅保证流程可通）"""
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        dim = self._dim or 256
        vec = []
        for i in range(dim):
            idx = i % len(h)
            val = int(h[idx], 16) / 15.0 - 0.5
            vec.append(val)
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
