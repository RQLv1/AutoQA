import re
from pathlib import Path

from pipeline.pipeline_final_refine import refine_final_question
from pipeline.pipeline_review import review_question
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
from utils.terminal import print_final_input, print_final_summary


_OPTION_SEGMENT_RE = re.compile(r"([A-D])[\\.|\\)|、|:：]\\s*([^\\n]{0,80})")
_CONDITION_RE = re.compile(r"(若|如果|当|则|按|根据|阈值|公式|计算|换算|分级|判定|规则|标准|区间|≥|≤|>|<|=)")
_FORBIDDEN_STEM_RE = re.compile(r"(【|】|已知条件|判据|任务说明|提示|步骤|解题思路|\\(1\\)|\\(2\\)|\\(3\\))")
_GUIDE_PHRASE_RE = re.compile(r"(保留两位小数|代入公式|依次求出|依次计算|请按步骤|先.{0,6}再)")
_RULE_KEYWORDS = ("规则", "阈值", "定义", "分级", "判定", "条件", "公式")
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

    first_option = matches[0].start() if matches else len(question)
    stem = question[:first_option]
    condition_hits = len(_CONDITION_RE.findall(stem))
    numeric_hits = len(re.findall(r"\\d+(?:\\.\\d+)?", stem))
    condition_total = condition_hits + numeric_hits
    equation_count = stem.count("=")
    if equation_count > 2:
        reasons.append("too many equations")
    if _FORBIDDEN_STEM_RE.search(stem):
        reasons.append("forbidden prompt cues")
    if _GUIDE_PHRASE_RE.search(stem):
        reasons.append("guided phrasing detected")
    sentences = [s.strip() for s in re.split(r"[。！？!?]", stem) if s.strip()]
    rule_sentences = sum(
        1 for sentence in sentences if any(keyword in sentence for keyword in _RULE_KEYWORDS)
    )
    if rule_sentences > 2:
        reasons.append("too many rule sentences")
    if "等级" in stem and "按文中等级阈值划分" not in stem:
        reasons.append("grade threshold detail in stem")

    if not any(anchor in question for anchor in _VISUAL_ANCHORS):
        reasons.append("missing visual anchor cues")

    if REQUIRE_CROSS_MODAL and not cross_modal_used:
        reasons.append("cross-modal not used")

    if num_hops < 2:
        reasons.append("insufficient hops")

    stats = {
        "conditions": condition_total,
        "equations": equation_count,
        "rule_sentences": rule_sentences,
        "has_visual_anchor": any(anchor in question for anchor in _VISUAL_ANCHORS),
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

    refine_attempts = 0
    max_refine_attempts = 2
    difficulty_metrics: dict[str, object] = {}
    structure_reasons: list[str] = []
    structure_stats: dict[str, int | bool] = {}
    reflect_feedback = ""
    review_raw = None
    review_passed = None
    refine_feedback = ""

    print_final_input(
        steps_count=len(compress_steps),
        cross_modal_used=cross_modal_used,
        refine_attempts=refine_attempts,
        max_refine_attempts=max_refine_attempts,
    )

    while True:
        structure_ok, structure_reasons, structure_stats = _check_final_structure(
            stage_final.question,
            cross_modal_used=cross_modal_used,
            num_hops=len(compress_steps),
        )
        if not structure_ok:
            if refine_attempts >= max_refine_attempts:
                difficulty_metrics = {
                    "structure_passed": False,
                    "structure_reasons": structure_reasons,
                    "structure_stats": structure_stats,
                }
                reflect_feedback = f"结构检查未通过: {', '.join(structure_reasons)}"
                break
            refine_attempts += 1
            style_reasons = {
                "too many equations",
                "forbidden prompt cues",
                "guided phrasing detected",
                "too many rule sentences",
                "grade threshold detail in stem",
            }
            if any(reason in style_reasons for reason in structure_reasons):
                rewrite_hint = (
                    "保持同一考点与答案不变，把题干压缩为一个自然段，"
                    "仅保留必要的读图对象、两个基准值、以及一条简短规则（最多2句），"
                    "删除所有步骤与判据表。"
                )
                stage_final, refine_feedback = refine_final_question(
                    context=context,
                    steps=compress_steps,
                    image_path=image_path,
                    final=stage_final,
                    reason="style_violation",
                    review_raw=rewrite_hint,
                )
                get_details_logger().log_event(
                    "final_stage_refined",
                    {
                        "question": stage_final.question,
                        "answer": stage_final.answer,
                        "reasoning": stage_final.reasoning,
                        "reason": "style_violation",
                        "feedback": refine_feedback,
                    },
                )
            else:
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
                        "reason": "structure_check_failed",
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
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
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
                    "reason": "text_only_veto",
                },
            )
            continue

        if difficulty_metrics.get("medium_correct"):
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            stage_final, refine_feedback = refine_final_question(
                context=context,
                steps=compress_steps,
                image_path=image_path,
                final=stage_final,
                reason="medium_solved",
            )
            get_details_logger().log_event(
                "final_stage_refined",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "medium_solved",
                    "feedback": refine_feedback,
                },
            )
            continue

        review_raw, review_passed = review_question(
            stage_final.question,
            stage_final.answer,
            stage_final.reasoning,
            image_path,
        )
        if review_passed is False:
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            stage_final, refine_feedback = refine_final_question(
                context=context,
                steps=compress_steps,
                image_path=image_path,
                final=stage_final,
                reason="review_failed",
                review_raw=review_raw,
            )
            get_details_logger().log_event(
                "final_stage_refined",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "review_failed",
                    "feedback": refine_feedback,
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

    print_final_summary(
        final=stage_final,
        metrics=difficulty_metrics,
        review_passed=review_passed,
        refine_attempts=refine_attempts,
        max_refine_attempts=max_refine_attempts,
        structure_reasons=structure_reasons,
    )

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
        judge_flags={},
        reflect_feedback=reflect_feedback,
        review_raw=review_raw,
        review_passed=review_passed,
        refine_feedback=refine_feedback,
    )
