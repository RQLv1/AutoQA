import re


_OPTION_MARKER = re.compile(r"(?i)(?P<letter>[A-H])\s*[\.．、】【\)]\s*")


def _extract_options(question: str) -> list[str]:
    if not question:
        return []
    matches = list(_OPTION_MARKER.finditer(question))
    if len(matches) < 2:
        return []
    options: list[str] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(question)
        options.append(question[start:end].strip())
    return options


def infer_step_operator(question: str) -> str:
    if not question:
        return "unknown"

    text = question.lower()

    anomaly_cues = ["缺失", "遗漏", "多余", "冲突", "不一致", "错误", "不符合", "异常", "违规", "不合理"]
    if any(cue in question for cue in anomaly_cues):
        return "anomaly"

    distinction_cues = ["区别", "不同", "相较", "相比", "对比", "更符合", "更可能", "哪项更", "主要差异"]
    if any(cue in question for cue in distinction_cues):
        return "distinction"

    options = _extract_options(question)
    if options:
        numeric_like = 0
        for opt in options:
            if re.search(r"\d", opt):
                numeric_like += 1
                continue
            if re.search(r"[\+\-]?\d+(\.\d+)?\s*(%|℃|°c|kpa|mpa|nm|mm|cm|m|kg|g|mg|s|min|h)\b", opt, flags=re.I):
                numeric_like += 1
                continue
            if re.search(r"\b\d+(\.\d+)?\s*[-~～]\s*\d+(\.\d+)?\b", opt):
                numeric_like += 1
                continue
            if re.search(r"(高|中|低|一级|二级|三级|四级|i{1,4}|iv)\b", opt, flags=re.I):
                numeric_like += 1
        if numeric_like >= 2:
            return "calculation"

    calculation_cues = ["计算", "求", "估算", "阈值", "满足条件", "大于", "小于", "不超过", "至少", "最多"]
    if any(cue in question for cue in calculation_cues) or any(cue in text for cue in ["calculate", "threshold"]):
        return "calculation"

    return "other"


def is_low_quality_entity_matching(question: str) -> bool:
    if not question:
        return True
    operator = infer_step_operator(question)
    if operator in {"calculation", "distinction", "anomaly"}:
        return False

    low_quality_cues = [
        "是什么",
        "指的是",
        "下列哪项描述正确",
        "下列哪项正确",
        "下列哪个是",
        "属于",
        "定义",
        "说法正确",
    ]
    return any(cue in question for cue in low_quality_cues)
