import os

MODEL_STAGE_1 = os.getenv("MODEL_STAGE_1", "gemini-3-pro-preview")
MODEL_STAGE_2 = os.getenv("MODEL_STAGE_2", "gpt-51-1113-global")
MODEL_STAGE_3 = os.getenv("MODEL_STAGE_3", "gemini-3-pro-preview")
MODEL_SUM = os.getenv("MODEL_SUM", os.getenv("MODEL_STAGE_SUM", "gpt-51-1113-global"))
MODEL_SOLVE = os.getenv("MODEL_SOLVE", "gemini-3-pro-preview")
MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "gpt-51-1113-global")

API_BASE_URL = "https://idealab.alibaba-inc.com/api/openai/v1"
API_KEY = "e086b5a947c3c2651165617b22318df5"

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "5"))
QUESTION_LOG_PATH = os.getenv("QUESTION_LOG_PATH", "question_log.jsonl")
