from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    folder_names: list[str] = Field(default_factory=list)


class ChatSource(BaseModel):
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    model: str
    selected_folders: list[str]
    sources: list[ChatSource]
