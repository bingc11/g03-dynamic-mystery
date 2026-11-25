import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DB_CONN_URL = os.getenv("DB_CONN_URL")

INFERENCE_SERVICE = os.getenv("INFERENCE_SERVICE", "anthropic")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
OPENAI_COMPATIBLE = frozenset(("openai", "groq", "openrouter", "deepseek"))
API_KEY = os.getenv("DEEPSEEK_API_KEY" if INFERENCE_SERVICE == "deepseek" else "API_KEY")

if INFERENCE_SERVICE == "anthropic":
    MODEL = os.getenv("MODEL", "claude-3-haiku-20240307")
elif INFERENCE_SERVICE == "deepseek":
    MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
elif INFERENCE_SERVICE in OPENAI_COMPATIBLE:
    MODEL = os.getenv("MODEL", "gpt-3.5-turbo")
elif INFERENCE_SERVICE == "ollama":
    MODEL = os.getenv("MODEL", "llama2")
else:
    raise ValueError(f"Unknown inference service: {INFERENCE_SERVICE}")

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048" if INFERENCE_SERVICE == "deepseek" else "8192"))

# Increment this whenever we make changes to the prompts
PROMPTS_VERSION = "1.0.5"

MODEL_KEY = f"{MODEL}:{MAX_TOKENS}:{PROMPTS_VERSION}"

# Additional settings for specific services
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GROQ_API_BASE = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
