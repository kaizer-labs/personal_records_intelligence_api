from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chat import ChatResponse, ChatSource
from app.services.library import ChunkRecord, LibraryService
from app.services.ollama import OllamaClient, OllamaServiceError
from app.services.text_processing import build_excerpt, cosine_similarity, score_text


@dataclass
class RankedChunk:
    chunk_id: str
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    text: str
    score: float
    lexical_score: float
    semantic_score: float


class ChatService:
    def __init__(self, library_service: LibraryService, ollama_client: OllamaClient) -> None:
        self._library_service = library_service
        self._ollama_client = ollama_client

    def answer_question(self, *, question: str, folder_names: list[str]) -> ChatResponse:
        chunks = self._library_service.search_chunks(folder_names=folder_names or None)
        if not chunks:
            return ChatResponse(
                answer="I don't have any indexed documents yet. Add a folder or load the example document first.",
                model=self._ollama_client.chat_model,
                selected_folders=folder_names,
                sources=[],
            )

        ranked_chunks = self._rank_chunks(question=question, chunks=chunks)
        top_chunks = ranked_chunks[:6]
        if not top_chunks:
            return ChatResponse(
                answer="I couldn't find relevant passages in the selected folders. Try a more specific question or sync a folder with text-based documents.",
                model=self._ollama_client.chat_model,
                selected_folders=folder_names,
                sources=[],
            )

        system_prompt = (
            "You answer questions about the user's documents using only the provided context. "
            "If the answer is not supported by the context, say that clearly. "
            "Keep the answer concise, practical, and grounded in the sources."
        )
        context_blocks = []
        for index, chunk in enumerate(top_chunks, start=1):
            context_blocks.append(
                "\n".join(
                    [
                        f"Source {index}",
                        f"Folder: {chunk.folder_name}",
                        f"Document: {chunk.document_name}",
                        f"Path: {chunk.relative_path}",
                        "Excerpt:",
                        chunk.text,
                    ]
                )
            )

        user_prompt = "\n\n".join(
            [
                f"Question: {question}",
                "Context:",
                *context_blocks,
                "Answer using the context above. Mention the document name when it helps disambiguate.",
            ]
        )

        result = self._ollama_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        return ChatResponse(
            answer=result.content,
            model=result.model,
            selected_folders=folder_names,
            sources=[
                ChatSource(
                    document_id=chunk.document_id,
                    folder_name=chunk.folder_name,
                    document_name=chunk.document_name,
                    relative_path=chunk.relative_path,
                    excerpt=build_excerpt(chunk.text, question),
                    score=round(chunk.score, 2),
                )
                for chunk in top_chunks
            ],
        )

    def _rank_chunks(
        self,
        *,
        question: str,
        chunks: list[ChunkRecord],
    ) -> list[RankedChunk]:
        query_embedding: list[float] | None = None
        try:
            query_embedding = self._ollama_client.embed_text(question)
        except OllamaServiceError:
            query_embedding = None

        ranked = [
            self._build_ranked_chunk(question=question, chunk=chunk, query_embedding=query_embedding)
            for chunk in chunks
        ]

        ranked.sort(key=lambda item: item.score, reverse=True)
        positive_matches = [chunk for chunk in ranked if chunk.score > 0]
        if positive_matches:
            return positive_matches

        return ranked[:4]

    def _build_ranked_chunk(
        self,
        *,
        question: str,
        chunk: ChunkRecord,
        query_embedding: list[float] | None,
    ) -> RankedChunk:
        lexical_score = score_text(
            question,
            f"{chunk.document_name}\n{chunk.relative_path}\n{chunk.text}",
        ) + max(0.0, 1.0 - (chunk.chunk_index * 0.05))
        semantic_score = (
            cosine_similarity(query_embedding, chunk.embedding)
            if query_embedding and chunk.embedding
            else 0.0
        )
        lexical_component = min(lexical_score / 8.0, 1.5)
        semantic_component = max(semantic_score, 0.0) * 4.5

        return RankedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            folder_name=chunk.folder_name,
            document_name=chunk.document_name,
            relative_path=chunk.relative_path,
            text=chunk.text,
            score=lexical_component + semantic_component,
            lexical_score=lexical_score,
            semantic_score=semantic_score,
        )
