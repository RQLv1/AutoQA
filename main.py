from pathlib import Path

from pipeline import run_episode
from utils.config import GENQA_HARD_PATH, GENQA_SIMPLE_PATH, MAX_ROUNDS
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
    genqa_hard_path = Path(GENQA_HARD_PATH)
    generated_count = 0
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
        if metrics.get("structure_passed") is False:
            print("Final 结构检查未通过，直接废弃。")
            if generated_count >= max_attempts:
                print("达到最大尝试次数，停止。")
                break
            continue

        if metrics.get("text_only_veto"):
            print("发现文本捷径：Text-only 可解，直接废弃。")
            if generated_count >= max_attempts:
                print("达到最大尝试次数，停止。")
                break
            continue

        medium_correct = metrics.get("medium_correct", True)
        strong_correct = metrics.get("strong_correct", True)
        strong_text_only_correct = metrics.get("strong_text_only_correct", True)
        strong_no_image_correct = metrics.get("strong_no_image_correct", True)
        final_no_text_shortcut = not (strong_text_only_correct or strong_no_image_correct)

        if medium_correct:
            print("题目太简单：Medium Solver 做对了，直接废弃。")
            if generated_count >= max_attempts:
                print("达到最大尝试次数，停止。")
                break
            continue

        print("发现难题：Medium Solver 失败。")
        if not strong_correct:
            print("Strong Solver 失败：可能是超难题或错题。")
        else:
            print("Strong Solver 成功：中等难度题。")

        review_raw = episode.review_raw
        review_passed = episode.review_passed
        review_decision = None
        if not medium_correct:
            if review_passed is True:
                review_decision = "correct"
                if final_no_text_shortcut:
                    # 逻辑修改：
                    # Medium 错 (已在上方过滤)
                    # Strong 错 -> 存入 Hard
                    # Strong 对 -> 存入 Simple
                    if not strong_correct:
                        target_path = genqa_hard_path
                        print(f"[Review] 结果: correct -> {target_path} (Hard: Medium=X, Strong=X)")
                    else:
                        target_path = genqa_simple_path
                        print(f"[Review] 结果: correct -> {target_path} (Simple: Medium=X, Strong=O)")

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
                    hard_questions_found += 1
                    print(f"当前已收集难题: {hard_questions_found}/{target_hard_questions}")
                else:
                    print("[Review] 结果: text-only/no-image 可解，跳过入库")
            elif review_passed is False:
                review_decision = "incorrect"
                print("[Review] 结果: incorrect")
            else:
                review_decision = "unknown"
                print("[Review] 结果: unknown")

        if generated_count >= max_attempts:
            print("达到最大尝试次数，停止。")
            break

    print(f"\n生成结束。共尝试 {generated_count} 次，筛选出 {hard_questions_found} 道难题。")


if __name__ == "__main__":
    main()
