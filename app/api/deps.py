"""FastAPI dependencies — auth, services, etc."""

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings, Settings
from app.services.embedder import EmbeddingService
from app.services.rag import RAGService
from app.services.risk_calculator import RiskCalculator
from app.services.businesscase import BusinessCaseCalculator

# API Key authentication
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify the API key from the Authorization header."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    # Strip "Bearer " prefix
    key = api_key.replace("Bearer ", "").strip()
    if key != settings.architect_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return key


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def get_rag_service() -> RAGService:
    return RAGService()


def get_risk_calculator() -> RiskCalculator:
    return RiskCalculator()


def get_businesscase_calculator() -> BusinessCaseCalculator:
    return BusinessCaseCalculator()
