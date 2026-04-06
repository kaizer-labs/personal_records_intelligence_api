from typing import Literal

from pydantic import BaseModel, Field


FolderOrigin = Literal["api_examples", "browser_upload"]
FileStatus = Literal["ingested", "skipped"]


class DocumentSummary(BaseModel):
    id: str
    filename: str
    relative_path: str
    media_type: str
    char_count: int
    chunk_count: int
    updated_at: str


class FolderSummary(BaseModel):
    name: str
    origin: FolderOrigin
    document_count: int
    chunk_count: int
    updated_at: str
    documents: list[DocumentSummary] = Field(default_factory=list)


class ProcessedFileResult(BaseModel):
    folder_name: str
    relative_path: str
    filename: str
    status: FileStatus
    document_id: str | None = None
    char_count: int = 0
    chunk_count: int = 0
    reason: str | None = None


class FolderListResponse(BaseModel):
    folders: list[FolderSummary]


class FolderSyncResponse(BaseModel):
    folders: list[FolderSummary]
    processed_files: list[ProcessedFileResult]
