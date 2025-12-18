import os

MODEL_STAGE_1 = os.getenv("MODEL_STAGE_1", "gpt-5-chat-0807-global")
MODEL_STAGE_2 = os.getenv("MODEL_STAGE_2", "gpt-51-1113-global")
MODEL_STAGE_3 = os.getenv("MODEL_STAGE_3", "gemini-2.5-pro-06-17")
MODEL_SUM = os.getenv("MODEL_SUM", os.getenv("MODEL_STAGE_SUM", "gpt-51-1113-global"))

MODEL_SOLVE = os.getenv("MODEL_SOLVE", "gemini-2.5-pro-06-17")
MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "gpt-51-1113-global")

MODEL_SOLVE_MEDIUM = os.getenv("MODEL_SOLVE_MEDIUM", "gpt-5-mini-0807-global")
MODEL_SOLVE_STRONG = os.getenv("MODEL_SOLVE_STRONG", "claude_sonnet4_5")
MODEL_SOLVE_FINAL = os.getenv("MODEL_SOLVE_FINAL", MODEL_SOLVE_STRONG)

MODEL_JUDGE = os.getenv("MODEL_JUDGE", "gemini-2.5-pro-06-17")

API_BASE_URL = "https://idealab.alibaba-inc.com/api/openai/v1"
API_KEY = "e086b5a947c3c2651165617b22318df5"

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "5"))
QUESTION_LOG_PATH = os.getenv("QUESTION_LOG_PATH", "question_log.jsonl")
MAX_STEPS_PER_ROUND = int(os.getenv("MAX_STEPS_PER_ROUND", "6"))
MIN_HOPS = int(os.getenv("MIN_HOPS", "2"))
REQUIRE_CROSS_MODAL = os.getenv("REQUIRE_CROSS_MODAL", "true").lower() in {"1", "true", "yes"}
