import os

# =============================================================================
# 模型配置 (Model Configuration)
# =============================================================================
# 生成阶段使用的模型
MODEL_STAGE_1 = os.getenv("MODEL_STAGE_1", "gpt-51-1113-global")  # 阶段1：通常用于初始分析
MODEL_STAGE_2 = os.getenv("MODEL_STAGE_2", MODEL_STAGE_1)  # 阶段2：通常用于深入推理
MODEL_STAGE_3 = os.getenv("MODEL_STAGE_3", MODEL_STAGE_1)  # 阶段3：通常用于最终生成
# 视觉理解与知识抽取使用的模型
MODEL_VISION_KNOWLEDGE = os.getenv("MODEL_VISION_KNOWLEDGE", MODEL_STAGE_1)
# 汇总和通用任务使用的模型
MODEL_SUM = os.getenv("MODEL_SUM", os.getenv("MODEL_STAGE_SUM", "gemini-3-pro-preview"))

# 操作代理使用的模型
MODEL_OPERATE = os.getenv("MODEL_OPERATE", MODEL_STAGE_1)  # 默认操作模型
MODEL_OPERATE_DISTINCTION = os.getenv("MODEL_OPERATE_DISTINCTION", MODEL_OPERATE)  # 区分/辨析任务
MODEL_OPERATE_CALCULATION = os.getenv("MODEL_OPERATE_CALCULATION", MODEL_OPERATE)  # 计算任务

# 求解器模型 (Solver Models) - 用于评估题目难度
MODEL_SOLVE_MEDIUM = os.getenv("MODEL_SOLVE_MEDIUM", "gemini-3-flash-preview")  # 中等能力模型 (用于检测题目是否过简单)
MODEL_SOLVE_STRONG = os.getenv("MODEL_SOLVE_STRONG", "claude_sonnet4_5")  # 强能力模型 (用于确保题目可解)
# 评审模型 (Review Model) - 用于审核题目质量
MODEL_REVIEW = os.getenv("MODEL_REVIEW", MODEL_SOLVE_STRONG)

# 裁判模型 (Judge Model)
MODEL_JUDGE = os.getenv("MODEL_JUDGE", "gpt-51-1113-global")

# =============================================================================
# 生成参数配置 (Generation Parameters)
# =============================================================================
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0"))

# Max Tokens Definitions
# MAX_TOKENS_GRAPH_EXTRACTION = int(os.getenv("MAX_TOKENS_GRAPH_EXTRACTION", "16384"))
# MAX_TOKENS_SOLVER_VISION = int(os.getenv("MAX_TOKENS_SOLVER_VISION", "16384"))
# MAX_TOKENS_SOLVER_TEXT = int(os.getenv("MAX_TOKENS_SOLVER_TEXT", "16384"))
# MAX_TOKENS_AGENT = int(os.getenv("MAX_TOKENS_AGENT", "16384"))
# MAX_TOKENS_REVIEW = int(os.getenv("MAX_TOKENS_REVIEW", "16384"))
# MAX_TOKENS_FEEDBACK = int(os.getenv("MAX_TOKENS_FEEDBACK", "16384"))

# =============================================================================
# API 配置 (API Configuration)
# =============================================================================
API_BASE_URL = "https://idealab.alibaba-inc.com/api/openai/v1" # "https://idealab.alibaba-inc.com/api/openai/v1"
API_KEY = os.getenv("API_KEY")
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "5"))  # 接口调用最大重试次数
API_RETRY_SLEEP_SECONDS = int(os.getenv("API_RETRY_SLEEP_SECONDS", "5"))  # 重试间隔时间(秒)
API_RECONNECT_RETRIES = int(os.getenv("API_RECONNECT_RETRIES", "5"))  # 连接失败重试次数
API_RECONNECT_SLEEP_SECONDS = int(
    os.getenv("API_RECONNECT_SLEEP_SECONDS", "10")
)  # 连接失败重试间隔(秒)

# =============================================================================
# 生成流程配置 (Generation Process Configuration)
# =============================================================================
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "10"))  # 最大生成轮次
QUESTION_LOG_PATH = os.getenv("QUESTION_LOG_PATH", "question_log.jsonl")  # 过程日志文件路径
GENQA_SIMPLE_PATH = os.getenv("GENQA_SIMPLE_PATH", "genqa_simple.json")  # 简单/中等题目保存路径
GENQA_HARD_PATH = os.getenv("GENQA_HARD_PATH", "genqa_hard.json")  # 难题保存路径
DETAILS_PATH = os.getenv("DETAILS_PATH", "details.json")  # 终端与草稿信息日志

MAX_STEPS_PER_ROUND = int(os.getenv("MAX_STEPS_PER_ROUND", "6"))  # 每轮生成的最大推理步数
MIN_HOPS = int(os.getenv("MIN_HOPS", "5"))  # 最小推理跳数 (用于控制题目复杂度)
REQUIRE_CROSS_MODAL = os.getenv("REQUIRE_CROSS_MODAL", "true").lower() in {"1", "true", "yes"}  # 是否强制要求跨模态推理

VERIFY_STRICT = os.getenv("VERIFY_STRICT", "false").lower() in {"1", "true", "yes"}  # 是否启用严格验证

# =============================================================================
# 图模式配置 (Graph Mode Configuration)
# =============================================================================
ENABLE_GRAPH_MODE = os.getenv("ENABLE_GRAPH_MODE", "true").lower() in {"1", "true", "yes"}  # 是否启用图模式构建上下文
DOC_CHUNK_WORDS = int(os.getenv("DOC_CHUNK_WORDS", "160"))  # 文档分块大小 (词数)
REQUIRE_DISTINCT_SOURCES = os.getenv("REQUIRE_DISTINCT_SOURCES", "false").lower() in {"1", "true", "yes"}  # 是否要求信息来源不同
PATH_SAMPLER = os.getenv("PATH_SAMPLER", "rbfs")  # 路径采样算法 (如: rbfs)
MAX_SHORTCUT_EDGES = int(os.getenv("MAX_SHORTCUT_EDGES", "10"))  # 图中允许的最大快捷边数量
