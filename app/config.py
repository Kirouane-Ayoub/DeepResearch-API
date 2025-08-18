import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv(override=True)


class Settings(BaseSettings):
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True

    # LLM Provider Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")  # "gemini" or "ollama"
    # Google GenAI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # Ollama Configuration
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    OLLAMA_REQUEST_TIMEOUT: float = float(os.getenv("OLLAMA_REQUEST_TIMEOUT", "120.0"))
    OLLAMA_CONTEXT_WINDOW: int = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "8000"))

    # Research Configuration
    DEFAULT_TIMEOUT: int = 300
    DEFAULT_MAX_REVIEW_CYCLES: int = 3
    MAX_CONCURRENT_SESSIONS: int = 10

    # Logging Configuration
    LOG_LEVEL: str = "INFO"

    # CORS Configuration
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
