"""
从 PDF 中裁剪 image, chart, figure_title 等元素，并按原始位置组合成新图。
"""
import json
import os
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import Image

# 导入图片过滤模块
from .image_filter import is_junk_image, llm_check_image_validity

# 配置路径
PDF_PATH = Path(
    "/Users/lvrenquan/worksapce/任务/AutoQA/data/pdf/"
    "Adv Funct Materials - 2025 - Tian - Rb Doping and Lattice Strain Synergistically Engineering "
    "Oxygen Vacancies in TiO2 for.pdf"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / PDF_PATH.stem
IMAGES_DIR = OUTPUT_DIR / "images"
RENDER_SCALE = 2.0

# 需要提取和组合的元素类型
TARGET_LABELS = {"image", "chart", "figure_title"}


def normalize_box(box: list[float] | None) -> list[float] | None:
    """规范化边界框坐标为 [x0, y0, x1, y1]"""
    if not box or len(box) != 4:
        return None
    x0, y0, x1, y1 = [v for v in box]
    return [x0, y0, x1, y1]


def render_pdf_page(
    page: pdfplumber.page.Page, detect_size: tuple[int, int] | None
) -> tuple[Image.Image, tuple[int, int], tuple[float, float]]:
    """
    渲染 PDF 页面为图片。

    返回: (图片对象, (宽度, 高度), (x缩放比, y缩放比))
    """
    if detect_size:
        det_w, det_h = detect_size
        dpi_x = det_w * 72 / page.width if page.width else 72
        dpi_y = det_h * 72 / page.height if page.height else 72
        resolution = max(dpi_x, dpi_y, 72)
    else:
        resolution = 72 * RENDER_SCALE
        det_w, det_h = (page.width, page.height)

    page_image = page.to_image(resolution=resolution)
    image = page_image.original
    ratio_x = image.width / det_w if det_w else 1
    ratio_y = image.height / det_h if det_h else 1
    return image, (image.width, image.height), (ratio_x, ratio_y)


def get_annotated_image_path(layout_dir: Path, input_path: str, page_index: int) -> Path | None:
    """获取标注图片的路径"""
    pdf_stem = Path(input_path).stem
    annotated_img_path = layout_dir / f"{pdf_stem}_{page_index}_res.png"

    if not annotated_img_path.exists() and pdf_stem:
        annotated_img_path = layout_dir / f"{pdf_stem}_res.png"

    if annotated_img_path.exists():
        return annotated_img_path
    return None


def crop_element(
    page_image: Image.Image,
    box: dict[str, Any],
    render_size: tuple[int, int],
    scale_ratio: tuple[float, float]
) -> tuple[Image.Image, tuple[int, int, int, int]] | None:
    """
    从页面图片中裁剪单个元素。

    返回: (裁剪后的图片, (x0, y0, x1, y1)在渲染图上的实际坐标) 或 None
    """
    layout_coords = box.get("coordinate", [])
    norm_box = normalize_box(layout_coords)
    if not norm_box:
        return None

    render_w, render_h = render_size
    ratio_x, ratio_y = scale_ratio

    x0, y0, x1, y1 = norm_box
    # 转换到渲染图坐标
    x0 = int(round(x0 * ratio_x))
    y0 = int(round(y0 * ratio_y))
    x1 = int(round(x1 * ratio_x))
    y1 = int(round(y1 * ratio_y))

    # 添加小边距
    margin_x = int((x1 - x0) * 0.02)
    margin_y = int((y1 - y0) * 0.02)
    x0 = max(0, x0 - margin_x)
    y0 = max(0, y0 - margin_y)
    x1 = min(render_w, x1 + margin_x)
    y1 = min(render_h, y1 + margin_y)

    crop = page_image.crop((x0, y0, x1, y1)).convert("RGB")
    return crop, (x0, y0, x1, y1)


def assemble_page_elements(
    elements: list[tuple[Image.Image, tuple[int, int, int, int], str]],
    render_size: tuple[int, int]
) -> Image.Image:
    """
    将裁剪的元素按原始位置组合，并裁剪出最小包含区域。

    Args:
        elements: [(裁剪的图片, (x0, y0, x1, y1), label), ...]
        render_size: 渲染图尺寸

    Returns:
        组合后的图片
    """
    render_w, render_h = render_size

    # 1. 创建全尺寸画布 (保持是为了定位准确)
    canvas = Image.new("RGB", (render_w, render_h), color="white")

    if not elements:
        return canvas

    # 初始化包围盒坐标
    min_x, min_y = render_w, render_h
    max_x, max_y = 0, 0

    # 2. 粘贴并更新包围盒
    for crop_img, (x0, y0, x1, y1), _label in elements:
        canvas.paste(crop_img, (x0, y0))

        # 更新有效区域的边界
        min_x = min(min_x, x0)
        min_y = min(min_y, y0)
        max_x = max(max_x, x1)
        max_y = max(max_y, y1)

    # 3. 增加一点 Padding (边距)，避免切得太死
    padding = 10
    crop_x0 = max(0, min_x - padding)
    crop_y0 = max(0, min_y - padding)
    crop_x1 = min(render_w, max_x + padding)
    crop_y1 = min(render_h, max_y + padding)

    # 4. 裁剪画布，只保留有内容的部分
    # 如果坐标无效（比如没有元素），则返回原图或空白图
    if crop_x1 > crop_x0 and crop_y1 > crop_y0:
        return canvas.crop((crop_x0, crop_y0, crop_x1, crop_y1))

    return canvas


def assemble_elements_from_res(
    pdf_path: Path,
    layout_dir: Path,
    images_dir: Path,
    target_labels: set[str] = TARGET_LABELS
) -> int:
    """
    从所有 res_*.json 中提取指定类型的元素，并按原始位置组合成新图。

    Args:
        pdf_path: PDF 文件路径
        layout_dir: 包含 res_*.json 的目录
        images_dir: 输出图片目录
        target_labels: 需要提取的元素类型集合

    Returns:
        保存的组合图数量
    """
    json_files = sorted(layout_dir.glob("res_*.json"))
    if not json_files:
        print("未找到 res_*.json，跳过元素组合。")
        return 0

    images_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    with pdfplumber.open(pdf_path) as pdf:
        for json_file in json_files:
            data = json.loads(json_file.read_text(encoding="utf-8"))

            # 筛选出目标类型的元素
            target_boxes = [
                b for b in data.get("boxes", [])
                if b.get("label") in target_labels
            ]

            if not target_boxes:
                continue

            # 获取页面索引
            page_index = data.get("page_index")
            input_path = data.get("input_path", "")
            if page_index is None:
                name = json_file.stem
                if name.startswith("res_") and name[4:].isdigit():
                    page_index = int(name[4:])
                else:
                    page_index = 0
            page_index = int(page_index)

            # 检查页面索引是否有效
            if page_index < 0 or page_index >= len(pdf.pages):
                print(f"跳过无效页面索引: {page_index}")
                continue

            page = pdf.pages[page_index]

            # 获取检测图尺寸
            annotated_img_path = get_annotated_image_path(layout_dir, input_path, page_index)
            detect_size = None
            if annotated_img_path:
                with Image.open(annotated_img_path) as ann_img:
                    detect_size = ann_img.size

            # 渲染 PDF 页面
            page_image, render_size, scale_ratio = render_pdf_page(page, detect_size)

            # 裁剪所有目标元素
            elements = []
            for box in target_boxes:
                result = crop_element(page_image, box, render_size, scale_ratio)
                if result:
                    crop_img, coords = result
                    label = box.get("label", "unknown")
                    elements.append((crop_img, coords, label))

            if not elements:
                continue

            # 组合元素到新画布
            assembled_img = assemble_page_elements(elements, render_size)

            # 保存组合后的图片
            pdf_stem = Path(input_path).stem if input_path else pdf_path.stem
            out_path = images_dir / f"{pdf_stem}_page_{page_index}_assembled.png"
            assembled_img.save(out_path)

            # === 新增过滤逻辑 ===
            # 使用推荐参数：过滤小图标和空白图
            is_junk, reason = is_junk_image(
                str(out_path),
                min_size=(150, 150),
                max_white_ratio=0.92,
                min_entropy=3.0
            )

            if is_junk:
                print(f"  ✗ 过滤无效图片: {reason}")
                os.remove(out_path)  # 删除无效图片
                # 不增加计数，跳过此图片
            else:
                count += 1
                print(f"  ✓ 页面 {page_index}: 组合了 {len(elements)} 个元素 → {out_path.name}")
                # (可选) 如果需要更严格的LLM检查，可以取消下面的注释
                # 使用配置文件中的 MODEL_SOLVE_MEDIUM (gemini-3-flash-preview)
                # api_key = os.getenv("API_KEY")
                # if api_key and not llm_check_image_validity(str(out_path), api_key):
                #     print(f"  ✗ LLM判定为无效图片")
                #     os.remove(out_path)
                #     count -= 1
            # ===================

    return count


def main() -> None:
    """主函数：从 res_*.json 中提取并组合 image, chart, figure_title 元素"""
    print("=" * 60)
    print("开始组合 PDF 元素...")
    print(f"目标元素类型: {', '.join(sorted(TARGET_LABELS))}")
    print("=" * 60)

    if not OUTPUT_DIR.exists():
        print(f"输出目录不存在: {OUTPUT_DIR}")
        return

    if not any(OUTPUT_DIR.glob("res_*.json")):
        print(f"未找到 res_*.json 文件，请先运行 pdf2txt.py")
        return

    count = assemble_elements_from_res(PDF_PATH, OUTPUT_DIR, IMAGES_DIR, TARGET_LABELS)

    print("=" * 60)
    print(f"完成！共生成 {count} 张组合图")
    print(f"保存位置: {IMAGES_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
