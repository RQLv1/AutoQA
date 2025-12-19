import os

MODEL_STAGE_1 = os.getenv("MODEL_STAGE_1", "gpt-5-chat-0807-global")
MODEL_STAGE_2 = os.getenv("MODEL_STAGE_2", "claude_sonnet4_5")
MODEL_STAGE_3 = os.getenv("MODEL_STAGE_3", "gpt-51-1113-global")
MODEL_SUM = os.getenv("MODEL_SUM", os.getenv("MODEL_STAGE_SUM", "gpt-51-1113-global"))
MODEL_OPERATE = os.getenv("MODEL_OPERATE", MODEL_STAGE_2)
MODEL_OPERATE_DISTINCTION = os.getenv("MODEL_OPERATE_DISTINCTION", MODEL_OPERATE)
MODEL_OPERATE_CALCULATION = os.getenv("MODEL_OPERATE_CALCULATION", MODEL_OPERATE)

MODEL_SOLVE_MEDIUM = os.getenv("MODEL_SOLVE_MEDIUM", "gpt-5-mini-0807-global")
MODEL_SOLVE_STRONG = os.getenv("MODEL_SOLVE_STRONG", "claude_sonnet4_5")
MODEL_REVIEW = os.getenv("MODEL_REVIEW", MODEL_SOLVE_STRONG)

MODEL_JUDGE = os.getenv("MODEL_JUDGE", "gpt-51-1113-global")

API_BASE_URL = "https://idealab.alibaba-inc.com/api/openai/v1"
API_KEY = "e086b5a947c3c2651165617b22318df5"
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "5"))
API_RETRY_SLEEP_SECONDS = int(os.getenv("API_RETRY_SLEEP_SECONDS", "5"))

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "10"))
QUESTION_LOG_PATH = os.getenv("QUESTION_LOG_PATH", "question_log.jsonl")
GENQA_SIMPLE_PATH = os.getenv("GENQA_SIMPLE_PATH", "genqa_simple.json")
GENQA_HARD_PATH = os.getenv("GENQA_HARD_PATH", "genqa_hard.json")
MAX_STEPS_PER_ROUND = int(os.getenv("MAX_STEPS_PER_ROUND", "4"))
MIN_HOPS = int(os.getenv("MIN_HOPS", "3"))
MAX_HARDEN_ATTEMPTS = int(os.getenv("MAX_HARDEN_ATTEMPTS", "3"))
HARDEN_MODE = os.getenv("HARDEN_MODE", "calc_first")
REQUIRE_CROSS_MODAL = os.getenv("REQUIRE_CROSS_MODAL", "true").lower() in {"1", "true", "yes"}

VERIFY_STRICT = os.getenv("VERIFY_STRICT", "false").lower() in {"1", "true", "yes"}

ENABLE_GRAPH_MODE = os.getenv("ENABLE_GRAPH_MODE", "true").lower() in {"1", "true", "yes"}
DOC_CHUNK_WORDS = int(os.getenv("DOC_CHUNK_WORDS", "160"))
REQUIRE_DISTINCT_SOURCES = os.getenv("REQUIRE_DISTINCT_SOURCES", "true").lower() in {"1", "true", "yes"}
PATH_SAMPLER = os.getenv("PATH_SAMPLER", "rbfs")
MAX_SHORTCUT_EDGES = int(os.getenv("MAX_SHORTCUT_EDGES", "0"))
