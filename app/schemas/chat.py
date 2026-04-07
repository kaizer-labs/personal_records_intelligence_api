from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    folder_names: list[str] = Field(default_factory=list)
    conversation_id: str | None = None


class ChatSource(BaseModel):
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    conversation_id: str
    conversation_title: str
    answer: str
    model: str
    selected_folders: list[str]
    sources: list[ChatSource]


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    meta: str | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    created_at: str


class ChatConversationSummary(BaseModel):
    id: str
    title: str
    folder_names: list[str] = Field(default_factory=list)
    preview: str | None = None
    message_count: int
    updated_at: str


class ChatConversationListResponse(BaseModel):
    conversations: list[ChatConversationSummary]


class ChatConversationDetailResponse(BaseModel):
    conversation: ChatConversationSummary
    messages: list[ChatMessage]
