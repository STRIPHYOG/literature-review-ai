"""
Hybrid retrieval system combining BM25 (sparse) and dense vector embeddings.
Includes Qdrant vector indexing and cross-encoder reranking.
"""

import numpy as np
import structlog
from typing import List, Dict, Any, Optional
from uuid import UUID
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class HybridRetriever:
    """
    Hybrid retrieval combining BM25 sparse search with dense vector similarity.
    Uses cross-encoder for reranking to maximize relevance.
    """

    def __init__(self):
        # Dense embedding model
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()

        # Cross-encoder reranker
        self.reranker = CrossEncoder(settings.reranker_model)

        # Qdrant vector DB client
        self.qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

        # BM25 index (in-memory per session)
        self._bm25_indices: Dict[str, dict] = {}

        logger.info(
            "HybridRetriever initialized",
            embedding_model=settings.embedding_model,
            embedding_dim=self.embedding_dim,
            reranker=settings.reranker_model,
        )

    def _get_collection_name(self, session_id: str) -> str:
        """Get the Qdrant collection name for a session."""
        return f"{settings.qdrant_collection}_{session_id.replace('-', '_')}"

    def index_chunks(self, chunks: list, session_id: str):
        """
        Index all chunks for a session:
        1. Create embeddings and store in Qdrant
        2. Build BM25 index
        """
        if not chunks:
            logger.warning("No chunks to index", session_id=session_id)
            return

        collection_name = self._get_collection_name(session_id)

        # Create Qdrant collection
        try:
            self.qdrant.delete_collection(collection_name)
        except Exception:
            pass

        self.qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.embedding_dim,
                distance=Distance.COSINE,
            ),
        )

        # Generate embeddings in batches
        batch_size = 64
        texts = [c.content for c in chunks]
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embedding_model.encode(batch, show_progress_bar=False)
            all_embeddings.extend(embeddings)

        # Store in Qdrant
        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            points.append(PointStruct(
                id=idx,
                vector=embedding.tolist(),
                payload={
                    "chunk_id": str(chunk.id),
                    "paper_id": str(chunk.paper_id),
                    "content": chunk.content,
                    "section_name": chunk.section_name,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                },
            ))

        # Upload in batches
        for i in range(0, len(points), 100):
            self.qdrant.upsert(
                collection_name=collection_name,
                points=points[i:i + 100],
            )

        # Update embedding IDs in chunks
        for idx, chunk in enumerate(chunks):
            chunk.embedding_id = str(idx)

        # Build BM25 index
        tokenized_corpus = [text.lower().split() for text in texts]
        self._bm25_indices[session_id] = {
            "bm25": BM25Okapi(tokenized_corpus),
            "chunks": chunks,
            "texts": texts,
        }

        logger.info(
            "Chunks indexed",
            session_id=session_id,
            collection=collection_name,
            chunk_count=len(chunks),
        )

    def retrieve(
        self,
        query: str,
        session_id: str,
        top_k: int = 20,
        rerank_top_k: int = 10,
        exclude_paper_id: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval with reranking:
        1. BM25 sparse retrieval (top_k candidates)
        2. Dense vector retrieval (top_k candidates)
        3. Score fusion (RRF)
        4. Cross-encoder reranking (final top_k)
        """
        collection_name = self._get_collection_name(session_id)

        # ─── Dense Vector Search ───
        query_embedding = self.embedding_model.encode(query).tolist()

        search_filter = None
        if exclude_paper_id:
            search_filter = Filter(
                must_not=[
                    FieldCondition(key="paper_id", match=MatchValue(value=exclude_paper_id))
                ]
            )

        try:
            dense_results = self.qdrant.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=search_filter,
            )
        except Exception as e:
            logger.warning("Dense search failed", error=str(e))
            dense_results = []

        # ─── BM25 Sparse Search ───
        bm25_results = []
        if session_id in self._bm25_indices:
            bm25_data = self._bm25_indices[session_id]
            tokenized_query = query.lower().split()
            bm25_scores = bm25_data["bm25"].get_scores(tokenized_query)

            # Get top-k BM25 results
            top_indices = np.argsort(bm25_scores)[::-1][:top_k]
            for idx in top_indices:
                if bm25_scores[idx] > 0:
                    chunk = bm25_data["chunks"][idx]
                    if exclude_paper_id and str(chunk.paper_id) == exclude_paper_id:
                        continue
                    bm25_results.append({
                        "chunk_id": str(chunk.id),
                        "paper_id": str(chunk.paper_id),
                        "content": chunk.content,
                        "section_name": chunk.section_name,
                        "page_number": chunk.page_number,
                        "bm25_score": float(bm25_scores[idx]),
                        "rank": len(bm25_results),
                    })

        # ─── Reciprocal Rank Fusion (RRF) ───
        fused_results = self._reciprocal_rank_fusion(dense_results, bm25_results, k=60)

        # ─── Cross-Encoder Reranking ───
        if fused_results and len(fused_results) > 1:
            reranked = self._rerank(query, fused_results, top_k=rerank_top_k)
        else:
            reranked = fused_results[:rerank_top_k]

        logger.info(
            "Retrieval completed",
            query_length=len(query),
            dense_count=len(dense_results),
            bm25_count=len(bm25_results),
            fused_count=len(fused_results),
            reranked_count=len(reranked),
        )

        return reranked

    def _reciprocal_rank_fusion(
        self, dense_results: list, bm25_results: list, k: int = 60
    ) -> List[Dict[str, Any]]:
        """Fuse results from dense and sparse search using RRF."""
        scores = {}
        result_map = {}

        # Score dense results
        for rank, result in enumerate(dense_results):
            chunk_id = result.payload.get("chunk_id", str(rank))
            rrf_score = 1.0 / (k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            result_map[chunk_id] = {
                "chunk_id": chunk_id,
                "paper_id": result.payload.get("paper_id"),
                "content": result.payload.get("content"),
                "section_name": result.payload.get("section_name"),
                "page_number": result.payload.get("page_number"),
                "dense_score": result.score,
            }

        # Score BM25 results
        for rank, result in enumerate(bm25_results):
            chunk_id = result["chunk_id"]
            rrf_score = 1.0 / (k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            if chunk_id not in result_map:
                result_map[chunk_id] = result
            result_map[chunk_id]["bm25_score"] = result.get("bm25_score", 0)

        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        fused = []
        for chunk_id in sorted_ids:
            item = result_map[chunk_id]
            item["fused_score"] = scores[chunk_id]
            fused.append(item)

        return fused

    def _rerank(self, query: str, candidates: List[Dict], top_k: int = 10) -> List[Dict]:
        """Rerank candidates using cross-encoder."""
        if not candidates:
            return []

        pairs = [(query, c.get("content", "")) for c in candidates]
        try:
            scores = self.reranker.predict(pairs)
        except Exception as e:
            logger.warning("Reranking failed", error=str(e))
            return candidates[:top_k]

        # Add rerank scores and sort
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)

        reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        return reranked[:top_k]

    def get_chunks_by_ids(self, chunk_ids: List[str], session_id: str) -> List[Dict]:
        """Retrieve specific chunks by their IDs."""
        collection_name = self._get_collection_name(session_id)
        results = []

        try:
            # Search for specific chunks
            for chunk_id in chunk_ids:
                search_results = self.qdrant.scroll(
                    collection_name=collection_name,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
                    ),
                    limit=1,
                )
                if search_results[0]:
                    point = search_results[0][0]
                    results.append(point.payload)
        except Exception as e:
            logger.warning("Chunk retrieval by IDs failed", error=str(e))

        return results
