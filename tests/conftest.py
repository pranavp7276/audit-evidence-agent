import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["LLM_DISABLE"] = "1"  # tests never call the model service; test_llm.py enables it against a mock
