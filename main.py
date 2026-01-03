import argparse
import subprocess
import sys
from pathlib import Path

from pipeline import run_episode
from utils.config import GENQA_MEDIUM_PATH, GENQA_SIMPLE_PATH, GENQA_STRONG_PATH, MAX_ROUNDS
from utils.details_logger import setup_details_logging
from utils.genqa import save_genqa_item


def _pick_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到文件: {', '.join(str(p) for p in candidates)}")


def _get_all_pdfs() -> list[Path]:
    """获取 data/pdf 目录下的所有 PDF 文件"""
    pdf_dir = Path("data/pdf")
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF 目录不存在: {pdf_dir}")
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"未找到 PDF 文件: {pdf_dir}")
    return pdf_files


def _process_pdf(pdf_path: Path) -> None:
    """运行 pdf2txt/run_pipeline.py 处理 PDF 文件"""
    print(f"\n>>> 正在处理 PDF: {pdf_path.name}")
    script_path = Path("pdf2txt/run_pipeline.py")
    if not script_path.exists():
        raise FileNotFoundError(f"脚本不存在: {script_path}")

    result = subprocess.run(
        [sys.executable, str(script_path), str(pdf_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"警告: PDF 处理失败\nstdout: {result.stdout}\nstderr: {result.stderr}")
    else:
        print(f"PDF 处理完成: {pdf_path.name}")


def _get_output_paths(pdf_path: Path) -> tuple[Path, list[Path]]:
    """根据 PDF 路径获取输出的 context 文本和所有图片"""
    output_dir = Path("output") / pdf_path.stem
    text_path = output_dir / "extracted.txt"
    images_dir = output_dir / "images"

    if not text_path.exists():
        raise FileNotFoundError(f"未找到文本文件: {text_path}")
    if not images_dir.exists():
        raise FileNotFoundError(f"未找到图片目录: {images_dir}")

    image_files = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
    if not image_files:
        raise FileNotFoundError(f"未找到图片文件: {images_dir}")

    return text_path, image_files


def _process_image(
    image_path: Path,
    context: str,
    args: argparse.Namespace,
    target_strong_questions: int = 3,
) -> tuple[int, int, int]:
    """
    处理单张图片，生成指定数量的 strong 题目
    返回: (simple_count, medium_count, strong_count)
    """
    genqa_simple_path = Path(GENQA_SIMPLE_PATH)
    genqa_medium_path = Path(GENQA_MEDIUM_PATH)
    genqa_strong_path = Path(GENQA_STRONG_PATH)

    generated_count = 0
    simple_questions_found = 0
    medium_questions_found = 0
    strong_questions_found = 0
    max_attempts = MAX_ROUNDS * 3
    feedback = ""
    previous_final_question = None

    print(f"\n>>> 正在处理图片: {image_path.name} (Target: {target_strong_questions} Strong Questions)")

    while strong_questions_found < target_strong_questions:
        generated_count += 1
        print(f"\n>>> 尝试第 {generated_count} 次生成 ...")

        episode = run_episode(
            context,
            image_path,
            feedback=feedback,
            previous_final_question=previous_final_question,
            prior_steps=None,
            mode=args.mode,
        )
        if episode.stage_final and episode.stage_final.question:
            previous_final_question = episode.stage_final.question
        feedback = episode.reflect_feedback or ""

        metrics = episode.difficulty_metrics
        medium_correct = metrics.get("medium_correct", False)
        medium_partial = metrics.get("medium_partial_correct", False)
        strong_correct = metrics.get("strong_correct")
        strong_text_only_correct = metrics.get("strong_text_only_correct", False)

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
            elif medium_partial:
                target_path = genqa_medium_path
                medium_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Medium: Medium=Partial，无错选)")
            elif strong_correct:
                target_path = genqa_medium_path
                medium_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Medium: Medium=X, Strong=O, TextOnly=X)")
            else:
                target_path = genqa_strong_path
                strong_questions_found += 1
                print(f"[Review] 结果: correct -> {target_path} (Strong: Medium=X, Strong=X, TextOnly=X)")

            save_genqa_item(
                target_path,
                {
                    "source": "final",
                    "image_path": str(image_path),
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
                f"Strong={strong_questions_found}/{target_strong_questions}"
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
        f"\n图片 {image_path.name} 处理完成。"
        f"共尝试 {generated_count} 次，"
        f"筛选出 Simple={simple_questions_found}, "
        f"Medium={medium_questions_found}, "
        f"Strong={strong_questions_found}。"
    )

    return simple_questions_found, medium_questions_found, strong_questions_found


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutoQA adversarial generation")
    parser.add_argument(
        "--mode",
        default="multi_select",
        choices=["multi_select", "single_select"],
        help="题型模式（支持多选题 multi_select 或单选题 single_select）",
    )
    parser.add_argument(
        "--target-strong-per-image",
        type=int,
        default=3,
        help="每张图片目标生成的 strong 题目数量（默认: 3）",
    )
    parser.add_argument(
        "--start-pdf-index",
        type=int,
        default=1,
        help="从第几个 PDF 开始处理（1-based，默认: 1）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    setup_details_logging()

    # 获取所有 PDF 文件
    pdf_files = _get_all_pdfs()
    print(f"=== 找到 {len(pdf_files)} 个 PDF 文件 ===")
    for i, pdf in enumerate(pdf_files, 1):
        print(f"  {i}. {pdf.name}")

    # 统计总计数
    total_simple = 0
    total_medium = 0
    total_strong = 0
    total_images = 0

    print(
        f"\n=== 开始批量处理 (mode={args.mode}, "
        f"每张图片目标: {args.target_strong_per_image} Strong Questions) ==="
    )

    start_index = args.start_pdf_index
    if start_index < 1 or start_index > len(pdf_files):
        raise ValueError(
            f"--start-pdf-index 超出范围: {start_index} (总数: {len(pdf_files)})"
        )

    # 遍历每个 PDF 文件
    for pdf_idx, pdf_path in enumerate(pdf_files[start_index - 1 :], start_index):
        print(f"\n{'='*80}")
        print(f"正在处理 PDF {pdf_idx}/{len(pdf_files)}: {pdf_path.name}")
        print(f"{'='*80}")

        try:
            # 1. 运行 pdf2txt/run_pipeline.py 处理 PDF
            _process_pdf(pdf_path)

            # 2. 获取输出的文本和图片
            text_path, image_files = _get_output_paths(pdf_path)
            context = text_path.read_text(encoding="utf-8")

            print(f"\n找到 {len(image_files)} 张图片:")
            for i, img in enumerate(image_files, 1):
                print(f"  {i}. {img.name}")

            # 3. 遍历每张图片
            for img_idx, image_path in enumerate(image_files, 1):
                print(f"\n{'-'*80}")
                print(
                    f"处理图片 {img_idx}/{len(image_files)} (PDF {pdf_idx}/{len(pdf_files)}): "
                    f"{image_path.name}"
                )
                print(f"{'-'*80}")

                simple, medium, strong = _process_image(
                    image_path,
                    context,
                    args,
                    target_strong_questions=args.target_strong_per_image,
                )

                total_simple += simple
                total_medium += medium
                total_strong += strong
                total_images += 1

                print(
                    f"\n累计已处理 {total_images} 张图片，"
                    f"总计收集: Simple={total_simple}, "
                    f"Medium={total_medium}, "
                    f"Strong={total_strong}"
                )

        except Exception as e:
            print(f"\n错误: 处理 PDF {pdf_path.name} 时发生异常: {e}")
            import traceback

            traceback.print_exc()
            continue

    print(f"\n{'='*80}")
    print("所有 PDF 处理完成!")
    print(
        f"共处理 {len(pdf_files)} 个 PDF 文件，{total_images} 张图片，"
        f"总计收集: Simple={total_simple}, Medium={total_medium}, Strong={total_strong}"
    )
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
