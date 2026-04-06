from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chat import ChatResponse, ChatSource
from app.services.library import LibraryService
from app.services.ollama import OllamaClient
from app.services.text_processing import build_excerpt, score_text


@dataclass(frozen=True)
class RankedChunk:
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    text: str
    score: float


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
        chunks: list[tuple[str, str, str, str, str, int]],
    ) -> list[RankedChunk]:
        ranked = [
            RankedChunk(
                document_id=document_id,
                folder_name=folder_name,
                document_name=document_name,
                relative_path=relative_path,
                text=text,
                score=score_text(question, f"{document_name}\n{relative_path}\n{text}") + max(0.0, 1.0 - (chunk_index * 0.05)),
            )
            for document_id, folder_name, document_name, relative_path, text, chunk_index in chunks
        ]

        ranked.sort(key=lambda item: item.score, reverse=True)
        positive_matches = [chunk for chunk in ranked if chunk.score > 0]
        if positive_matches:
            return positive_matches

        return ranked[:4]
