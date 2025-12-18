from pathlib import Path

from pipeline import run_episode, save_round_questions, try_solve_question
from prompts import build_analysis_prompt
from utils.api_client import call_text_model
from utils.config import MAX_ROUNDS, MODEL_ANALYSIS, MODEL_SOLVE_FINAL, QUESTION_LOG_PATH
from utils.parsing import parse_option_letter_optional


def _pick_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到文件: {', '.join(str(p) for p in candidates)}")


def main() -> None:
    image_path = _pick_existing_path([Path("data/test.png"), Path("test.png")])
    context_path = _pick_existing_path([Path("data/context.txt"), Path("context.txt")])
    context = context_path.read_text(encoding="utf-8")

    feedback = ""
    previous_feedback = None
    previous_final_question = None
    log_path = Path(QUESTION_LOG_PATH)
    for round_idx in range(1, MAX_ROUNDS + 1):
        print(f"\n=== 第 {round_idx} 轮生成 ===")
        stop_reason = None
        solver_raw = None
        solver_letter = None
        reflect_feedback = None

        episode = run_episode(context, image_path, feedback, previous_final_question)
        previous_final_question = episode.stage_final.question

        try:
            solver_raw, solver_letter = try_solve_question(
                context, episode.stage_final.question, image_path, MODEL_SOLVE_FINAL
            )
            standard_letter = parse_option_letter_optional(episode.stage_final.answer)
            if solver_letter:
                print("[Solve] 最终求解模型输出:", f"<answer>{solver_letter}</answer>")
            else:
                print(solver_raw)
            if not standard_letter:
                stop_reason = "standard_answer_parse_failed"
            elif not solver_letter:
                stop_reason = "solver_parse_failed"
            elif solver_letter != standard_letter:
                stop_reason = "solver_incorrect"
            else:
                analysis_prompt = build_analysis_prompt(
                    episode.stage_final.question,
                    episode.stage_final.answer,
                    solver_raw,
                )
                feedback = call_text_model(analysis_prompt, MODEL_ANALYSIS)
                reflect_feedback = feedback.strip()
                print("[Reflection] 难度提升指引:", feedback)
                if previous_feedback is not None and reflect_feedback == previous_feedback:
                    stop_reason = "feedback_converged"
                previous_feedback = reflect_feedback
        except Exception as exc:  # noqa: BLE001
            print(exc)
            stop_reason = "solve_error"

        save_round_questions(
            log_path,
            round_idx,
            episode,
            solver_final_pred=solver_letter,
            solver_final_raw=solver_raw,
            reflect_feedback=reflect_feedback,
            stop_reason=stop_reason,
        )

        if stop_reason:
            print(f"轮次终止原因: {stop_reason}")
            break
    else:
        print("已达到最大轮次，停止。")


if __name__ == "__main__":
    main()
