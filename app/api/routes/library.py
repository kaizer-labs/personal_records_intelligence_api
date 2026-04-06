from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from urllib.parse import unquote

from app.schemas.library import FolderListResponse, FolderSyncResponse
from app.services.library import IngestFile

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(request: Request) -> FolderListResponse:
    return request.app.state.library_service.list_folders()


@router.post("/examples/sync", response_model=FolderSyncResponse)
async def sync_examples(request: Request) -> FolderSyncResponse:
    return request.app.state.library_service.sync_example_files()


@router.post("/folders/upload", response_model=FolderSyncResponse)
async def upload_folder(
    request: Request,
    files: list[UploadFile] = File(...),
) -> FolderSyncResponse:
    ingest_files: list[IngestFile] = []

    for file in files:
        relative_path = file.filename or "uploaded-file"
        ingest_files.append(
            IngestFile(
                relative_path=relative_path,
                filename=Path(relative_path).name,
                content_type=file.content_type or "application/octet-stream",
                data=await file.read(),
            )
        )

    return request.app.state.library_service.sync_browser_uploads(ingest_files)


@router.delete("/documents/{document_id}", response_model=FolderListResponse)
async def delete_document(document_id: str, request: Request) -> FolderListResponse:
    return request.app.state.library_service.remove_document(document_id)


@router.delete("/folders/{folder_name}", response_model=FolderListResponse)
async def clear_folder(folder_name: str, request: Request) -> FolderListResponse:
    return request.app.state.library_service.clear_folder(unquote(folder_name))
