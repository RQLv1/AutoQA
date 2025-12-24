from pathlib import Path
import re

from pipeline.pipeline_solvers import evaluate_difficulty
from pipeline.pipeline_vision_knowledge import build_visual_knowledge
from prompts import build_analysis_prompt, build_final_compress_prompt, build_final_harden_prompt
from steps import derive_stage_results, generate_steps
from utils.api_client import call_text_model, call_vision_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_SUM,
    REQUIRE_CROSS_MODAL,
)
from utils.details_logger import get_details_logger
from utils.parsing import extract_tag_optional
from utils.schema import EpisodeResult, StageResult, StepResult


_OPTION_SEGMENT_RE = re.compile(r"([A-D])[\\.|\\)|、|:：]\\s*([^\\n]{0,80})")
_CONDITION_RE = re.compile(r"(若|如果|当|则|按|根据|阈值|公式|计算|换算|分级|判定|规则|标准|区间|≥|≤|>|<|=)")
_NUMERIC_RE = re.compile(r"\\d")
_GRADE_RE = re.compile(r"(一级|二级|三级|四级|甲|乙|丙|丁|高|中|低)")
_VISUAL_ANCHORS = [
    "图中",
    "图示",
    "图片",
    "图像",
    "图表",
    "曲线",
    "刻度",
    "指针",
    "箭头",
    "标注",
    "标记",
    "左上",
    "右上",
    "左下",
    "右下",
    "左侧",
    "右侧",
    "上方",
    "下方",
    "中心",
    "区域",
    "仪表",
    "面板",
    "屏幕",
    "读数",
    "坐标轴",
    "表格",
]


def _check_final_structure(
    question: str, *, cross_modal_used: bool, num_hops: int
) -> tuple[bool, list[str], dict[str, int | bool]]:
    reasons: list[str] = []
    matches = list(_OPTION_SEGMENT_RE.finditer(question))
    letters = {match.group(1) for match in matches}
    option_segments = [match.group(2) for match in matches]

    if not {"A", "B", "C", "D"}.issubset(letters):
        reasons.append("missing A-D options")

    first_option = matches[0].start() if matches else len(question)
    stem = question[:first_option]
    condition_hits = len(_CONDITION_RE.findall(stem))
    numeric_hits = len(re.findall(r"\\d+(?:\\.\\d+)?", stem))
    condition_total = condition_hits + numeric_hits
    if condition_total < 2:
        reasons.append("insufficient neutral conditions")

    numeric_like_options = 0
    for segment in option_segments:
        if _NUMERIC_RE.search(segment) or _GRADE_RE.search(segment):
            numeric_like_options += 1
    if numeric_like_options < 3:
        reasons.append("options not numeric/graded enough")

    if not any(anchor in question for anchor in _VISUAL_ANCHORS):
        reasons.append("missing visual anchor cues")

    if REQUIRE_CROSS_MODAL and not cross_modal_used:
        reasons.append("cross-modal not used")

    if num_hops < 2:
        reasons.append("insufficient hops")

    stats = {
        "conditions": condition_total,
        "numeric_like_options": numeric_like_options,
        "has_visual_anchor": any(anchor in question for anchor in _VISUAL_ANCHORS),
        "has_full_options": {"A", "B", "C", "D"}.issubset(letters),
    }
    return not reasons, reasons, stats


def run_final(prompt: str, image_path: Path, model: str) -> StageResult:
    raw = call_vision_model(prompt, image_path, model)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer = extract_tag_optional(raw, "answer") or ""
    reasoning = extract_tag_optional(raw, "reasoning")
    return StageResult(question=question, answer=answer, raw=raw, reasoning=reasoning)


def run_episode(
    context: str,
    image_path: Path,
    feedback: str = "",
    previous_final_question: str | None = None,
    prior_steps: list[StepResult] | None = None,
) -> EpisodeResult:
    visual_knowledge = build_visual_knowledge(image_path)
    steps, cross_modal_used = generate_steps(
        context,
        image_path,
        feedback,
        previous_final_question,
        visual_knowledge.summary,
        visual_knowledge.edges,
    )
    stage_1, stage_2, stage_3 = derive_stage_results(steps)

    compress_steps = steps if not prior_steps else [*prior_steps, *steps]
    final_prompt = build_final_compress_prompt(context, compress_steps, feedback)
    stage_final = run_final(final_prompt, image_path, MODEL_SUM)
    get_details_logger().log_event(
        "final_stage",
        {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "reasoning": stage_final.reasoning,
        },
    )

    harden_attempted = False
    difficulty_metrics: dict[str, object] = {}
    structure_reasons: list[str] = []
    structure_stats: dict[str, int | bool] = {}
    reflect_feedback = ""

    while True:
        structure_ok, structure_reasons, structure_stats = _check_final_structure(
            stage_final.question,
            cross_modal_used=cross_modal_used,
            num_hops=len(compress_steps),
        )
        if not structure_ok:
            if harden_attempted:
                difficulty_metrics = {
                    "structure_passed": False,
                    "structure_reasons": structure_reasons,
                    "structure_stats": structure_stats,
                }
                reflect_feedback = f"结构检查未通过: {', '.join(structure_reasons)}"
                break
            harden_attempted = True
            harden_prompt = build_final_harden_prompt(
                context,
                compress_steps,
                stage_final.question,
                stage_final.answer,
                "structure_check_failed: " + ", ".join(structure_reasons),
            )
            stage_final = run_final(harden_prompt, image_path, MODEL_SUM)
            get_details_logger().log_event(
                "final_stage_hardened",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                },
            )
            continue

        difficulty_metrics = evaluate_difficulty(
            stage_final,
            image_path,
            cross_modal_used,
            len(compress_steps),
        )
        difficulty_metrics["structure_passed"] = True
        difficulty_metrics["structure_reasons"] = structure_reasons
        difficulty_metrics["structure_stats"] = structure_stats

        if difficulty_metrics.get("text_only_veto"):
            if harden_attempted:
                break
            harden_attempted = True
            harden_prompt = build_final_harden_prompt(
                context,
                compress_steps,
                stage_final.question,
                stage_final.answer,
                "text-only solved",
            )
            stage_final = run_final(harden_prompt, image_path, MODEL_SUM)
            get_details_logger().log_event(
                "final_stage_hardened",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                },
            )
            continue

        if difficulty_metrics.get("medium_correct"):
            if harden_attempted:
                break
            harden_attempted = True
            harden_prompt = build_final_harden_prompt(
                context,
                compress_steps,
                stage_final.question,
                stage_final.answer,
                "medium solver solved",
            )
            stage_final = run_final(harden_prompt, image_path, MODEL_SUM)
            get_details_logger().log_event(
                "final_stage_hardened",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                },
            )
            continue

        break

    print("[Final] Compress 完成")
    print(stage_final.question)
    print("标准答案:", stage_final.answer)

    if difficulty_metrics.get("structure_passed") is False:
        print("[Final] 结构检查未通过:", ", ".join(structure_reasons))
    else:
        print(
            "[Final] Difficulty 评估:",
            f"medium_correct={difficulty_metrics.get('medium_correct')}",
            f"strong_correct={difficulty_metrics.get('strong_correct')}",
            f"score={difficulty_metrics.get('difficulty_score')}",
        )
        if not (
            difficulty_metrics.get("medium_correct", False)
            and difficulty_metrics.get("strong_correct", False)
        ) and stage_final.reasoning:
            print(f"推理过程: <reasoning>{stage_final.reasoning}</reasoning>")

    if difficulty_metrics.get("structure_passed") is not False:
        feedback_prompt = build_analysis_prompt(
            stage_final.question,
            stage_final.answer,
            str(difficulty_metrics.get("medium_raw") or ""),
        )
        reflect_feedback = call_text_model(
            feedback_prompt,
            MODEL_SUM,
            temperature=DEFAULT_TEMPERATURE,
        ).strip()
        if reflect_feedback:
            print("[Final] 反馈:", reflect_feedback)
    elif reflect_feedback:
        print("[Final] 反馈:", reflect_feedback)

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
        judge_flags={},
        reflect_feedback=reflect_feedback,
    )
