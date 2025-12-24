from pathlib import Path

from pipeline import run_episode
from utils.config import GENQA_HARD_PATH, GENQA_MEDIUM_PATH, GENQA_SIMPLE_PATH, MAX_ROUNDS
from utils.details_logger import setup_details_logging
from utils.genqa import save_genqa_item


def _pick_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到文件: {', '.join(str(p) for p in candidates)}")


def main() -> None:
    setup_details_logging()
    image_path = _pick_existing_path([Path("data/test.png"), Path("test.png")])
    context_path = _pick_existing_path([Path("data/context.txt"), Path("context.txt")])
    context = context_path.read_text(encoding="utf-8")

    genqa_simple_path = Path(GENQA_SIMPLE_PATH)
    genqa_medium_path = Path(GENQA_MEDIUM_PATH)
    genqa_hard_path = Path(GENQA_HARD_PATH)
    generated_count = 0
    simple_questions_found = 0
    medium_questions_found = 0
    hard_questions_found = 0
    target_hard_questions = 5
    max_attempts = MAX_ROUNDS * 3
    feedback = ""
    previous_final_question = None

    print(f"=== 开始对抗式生成模式 (Target: {target_hard_questions} Hard Questions) ===")

    while hard_questions_found < target_hard_questions:
        generated_count += 1
        print(f"\n>>> 尝试第 {generated_count} 次生成 ...")

        episode = run_episode(
            context,
            image_path,
            feedback=feedback,
            previous_final_question=previous_final_question,
            prior_steps=None,
        )
        if episode.stage_final and episode.stage_final.question:
            previous_final_question = episode.stage_final.question
        feedback = episode.reflect_feedback or ""

        metrics = episode.difficulty_metrics
        medium_correct = metrics.get("medium_correct", False)
        strong_correct = metrics.get("strong_correct")
        strong_text_only_correct = metrics.get("strong_text_only_correct", True)

        if strong_text_only_correct:
            print("发现文本捷径：Text-only 可解，直接废弃。")
            if generated_count >= max_attempts:
                print("达到最大尝试次数，停止。")
                break
            continue

        review_raw = episode.review_raw
        review_passed = episode.review_passed
        review_decision = None
        if review_passed is True:
            review_decision = "correct"
            if medium_correct:
                target_path = genqa_simple_path
                simple_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Simple: Medium=O, TextOnly=X)")
            elif strong_correct:
                target_path = genqa_medium_path
                medium_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Medium: Medium=X, Strong=O, TextOnly=X)")
            else:
                target_path = genqa_hard_path
                hard_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Hard: Medium=X, Strong=X, TextOnly=X)")

            save_genqa_item(
                target_path,
                {
                    "source": "final",
                    "question": episode.stage_final.question,
                    "answer": episode.stage_final.answer,
                    "reasoning": episode.stage_final.reasoning,
                    "difficulty_metrics": episode.difficulty_metrics,
                    "review_decision": review_decision,
                    "review_raw": review_raw,
                },
            )
            print(
                "当前已收集题目: "
                f"Simple={simple_questions_found}, "
                f"Medium={medium_questions_found}, "
                f"Hard={hard_questions_found}/{target_hard_questions}"
            )
        elif review_passed is False:
            review_decision = "incorrect"
            print("[Review] 结果: incorrect")
        else:
            review_decision = "unknown"
            print("[Review] 结果: unknown")

        if generated_count >= max_attempts:
            print("达到最大尝试次数，停止。")
            break

    print(
        "\n生成结束。"
        f"共尝试 {generated_count} 次，"
        f"筛选出 Simple={simple_questions_found}, "
        f"Medium={medium_questions_found}, "
        f"Hard={hard_questions_found}。"
    )


if __name__ == "__main__":
    main()
