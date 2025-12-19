from pathlib import Path

from pipeline import run_episode, save_round_questions
from utils.config import MAX_ROUNDS, QUESTION_LOG_PATH


def _pick_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到文件: {', '.join(str(p) for p in candidates)}")


def main() -> None:
    image_path = _pick_existing_path([Path("data/test.png"), Path("test.png")])
    context_path = _pick_existing_path([Path("data/context.txt"), Path("context.txt")])
    context = context_path.read_text(encoding="utf-8")

    log_path = Path(QUESTION_LOG_PATH)
    generated_count = 0
    hard_questions_found = 0
    target_hard_questions = 5
    max_attempts = MAX_ROUNDS * 3

    print(f"=== 开始对抗式生成模式 (Target: {target_hard_questions} Hard Questions) ===")

    while hard_questions_found < target_hard_questions:
        generated_count += 1
        print(f"\n>>> 尝试第 {generated_count} 次生成 ...")

        episode = run_episode(context, image_path, feedback="", previous_final_question=None)

        metrics = episode.difficulty_metrics
        medium_correct = metrics.get("medium_correct", True)
        strong_correct = metrics.get("strong_correct", True)

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

        save_round_questions(
            log_path,
            hard_questions_found + 1,
            episode,
            solver_final_pred=metrics.get("strong_pred"),
            solver_final_raw=metrics.get("strong_raw"),
            reflect_feedback="adversarial_filter_passed",
            stop_reason="success_hard_question",
        )

        hard_questions_found += 1
        if generated_count >= max_attempts:
            print("达到最大尝试次数，停止。")
            break

    print(f"\n生成结束。共尝试 {generated_count} 次，筛选出 {hard_questions_found} 道难题。")


if __name__ == "__main__":
    main()
