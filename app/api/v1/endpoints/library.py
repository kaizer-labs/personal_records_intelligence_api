from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.deps import LibraryServiceDep
from app.schemas.library import FolderListResponse, FolderSyncResponse
from app.services.library import IngestFile

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(library_service: LibraryServiceDep) -> FolderListResponse:
    return library_service.list_folders()


@router.post("/examples/sync", response_model=FolderSyncResponse)
async def sync_examples(library_service: LibraryServiceDep) -> FolderSyncResponse:
    return library_service.sync_example_files()


@router.post("/folders/upload", response_model=FolderSyncResponse)
async def upload_folder(
    library_service: LibraryServiceDep,
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

    return library_service.sync_browser_uploads(ingest_files)


@router.delete("/documents/{document_id}", response_model=FolderListResponse)
async def delete_document(
    document_id: str,
    library_service: LibraryServiceDep,
) -> FolderListResponse:
    return library_service.remove_document(document_id)


@router.get("/documents/{document_id}/file")
async def open_document_file(
    document_id: str,
    library_service: LibraryServiceDep,
) -> FileResponse:
    document = library_service.get_document_file(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document file not found.")

    return FileResponse(
        path=document.storage_path,
        media_type=document.media_type,
        filename=document.filename,
    )


@router.delete("/folders/{folder_name}", response_model=FolderListResponse)
async def clear_folder(
    folder_name: str,
    library_service: LibraryServiceDep,
) -> FolderListResponse:
    return library_service.clear_folder(unquote(folder_name))
