"""
Megregore Request/Response Models — Pydantic v2 models for the REST API.
"""

from typing import Optional

from pydantic import BaseModel, Field


# --- Auth Models ---

class SetupRequest(BaseModel):
    """First-run admin setup."""
    username: str = Field(default="admin", description="Admin username")
    password: str = Field(min_length=8, description="Admin password (min 8 chars)")


class LoginRequest(BaseModel):
    """Login request."""
    username: str = Field(description="Username")
    password: str = Field(description="Password")


class LoginResponse(BaseModel):
    """Successful login response."""
    token: str = Field(description="JWT access token")
    expires_at: str = Field(description="Token expiration (ISO 8601)")
    username: str = Field(description="Authenticated username")


class AuthStatus(BaseModel):
    """Auth status check response."""
    authenticated: bool
    username: Optional[str] = None
    setup_complete: bool


# --- Memory CRUD Models (Phase 4) ---

class CreateMemoryRequest(BaseModel):
    """Create a new memory."""
    content: str = Field(min_length=1, max_length=10000)
    memory_type: str = Field(
        default="experience",
        pattern=r"^(experience|fact|observation|reflection|insight|emotion|procedure)$",
    )
    importance: int = Field(default=5, ge=1, le=10)
    emotional_weight: float = Field(default=0.0, ge=-1.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    context: Optional[str] = Field(default=None, max_length=5000)


class UpdateMemoryRequest(BaseModel):
    """Update an existing memory. Only provided fields are changed."""
    content: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    memory_type: Optional[str] = Field(
        default=None,
        pattern=r"^(experience|fact|observation|reflection|insight|emotion|procedure)$",
    )
    importance: Optional[int] = Field(default=None, ge=1, le=10)
    emotional_weight: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    tags: Optional[list[str]] = None
    context: Optional[str] = Field(default=None, max_length=5000)
    is_permanent: Optional[bool] = None


class FadeRequest(BaseModel):
    """Fade a memory."""
    fade_amount: float = Field(default=0.3, ge=0.0, le=1.0)


class LinkRequest(BaseModel):
    """Link two memories."""
    source_id: int
    target_id: int
    link_type: str = Field(default="related", pattern=r"^(related|caused_by|evolved_from|contradicts)$")
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
