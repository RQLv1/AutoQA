import json
import math
from pathlib import Path

import pdfplumber
from PIL import Image
from paddleocr import LayoutDetection

PDF_PATH = Path(
    "/Users/lvrenquan/worksapce/任务/AutoQA/data/pdf/"
    "Adv Funct Materials - 2025 - Tian - Rb Doping and Lattice Strain Synergistically Engineering "
    "Oxygen Vacancies in TiO2 for.pdf"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / PDF_PATH.stem
TEXT_PATH = OUTPUT_DIR / "extracted.txt"
IMAGES_DIR = OUTPUT_DIR / "images"
MIN_SHORT_SIDE = 256
RENDER_SCALE = 2.0


def run_layout_detection(pdf_path: Path, out_dir: Path) -> None:
    model = LayoutDetection(model_name="PP-DocLayoutV2")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        output = model.predict(str(pdf_path), batch_size=1, layout_nms=True)
        for i, res in enumerate(output):
            res.print()
            res.save_to_img(save_path=str(out_dir))
            res.save_to_json(save_path=str(out_dir / f"res_{i}.json"))
        return
    except Exception as exc:
        print(f"PDF 版面检测失败，切换为按页图片模式: {exc}")

    page_dir = out_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            page_image = page.to_image(resolution=72 * RENDER_SCALE)
            img_path = page_dir / f"page_{page_index:03d}.png"
            page_image.save(str(img_path), format="PNG")
            output = model.predict(str(img_path), batch_size=1, layout_nms=True)
            for res in output:
                res.print()
                res.save_to_img(save_path=str(out_dir))
                json_path = out_dir / f"res_{page_index}.json"
                res.save_to_json(save_path=str(json_path))
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    data["page_index"] = page_index
                    data["input_path"] = str(img_path)
                    json_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass


def _normalize_box(box: list[float] | None) -> list[float] | None:
    if not box or len(box) != 4:
        return None
    x0, y0, x1, y1 = [v for v in box]
    return [x0, y0, x1, y1]


def render_pdf_page(
    page: pdfplumber.page.Page, detect_size: tuple[int, int] | None
) -> tuple[Image.Image, tuple[int, int], tuple[float, float]]:
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


def extract_text(pdf_path: Path, text_path: Path) -> None:
    pieces: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pieces.append(f"\n\n=== Page {idx} ===\n{text}")
    text_path.write_text("".join(pieces).lstrip(), encoding="utf-8")


def extract_layout_images(pdf_path: Path, layout_dir: Path, images_dir: Path) -> int:
    json_files = sorted(layout_dir.glob("res_*.json"))
    if not json_files:
        print("未找到 res_*.json，跳过版面图片裁切。")
        return 0

    count = 0
    with pdfplumber.open(pdf_path) as pdf:
        for json_file in json_files:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            figure_boxes = [
                b for b in data.get("boxes", []) if b.get("label") == "figure"
            ]
            if not figure_boxes:
                continue

            page_index = data.get("page_index")
            input_path = data.get("input_path", "")
            if page_index is None:
                name = json_file.stem
                if name.startswith("res_") and name[4:].isdigit():
                    page_index = int(name[4:])
                else:
                    page_index = 0
            page_index = int(page_index)
            pdf_stem = Path(input_path).stem
            annotated_img_path = layout_dir / f"{pdf_stem}_{page_index}_res.png"
            detect_size = None
            if not annotated_img_path.exists() and pdf_stem:
                annotated_img_path = layout_dir / f"{pdf_stem}_res.png"
            if annotated_img_path.exists():
                with Image.open(annotated_img_path) as ann_img:
                    detect_size = ann_img.size

            if page_index < 0 or page_index >= len(pdf.pages):
                continue
            page = pdf.pages[page_index]
            page_image, (render_w, render_h), (ratio_x, ratio_y) = render_pdf_page(
                page, detect_size
            )

            for idx, box in enumerate(figure_boxes):
                layout_coords = box.get("coordinate", [])
                norm_box = _normalize_box(layout_coords)
                if not norm_box:
                    continue

                x0, y0, x1, y1 = norm_box
                x0 = int(round(x0 * ratio_x))
                y0 = int(round(y0 * ratio_y))
                x1 = int(round(x1 * ratio_x))
                y1 = int(round(y1 * ratio_y))

                margin_x = int((x1 - x0) * 0.02)
                margin_y = int((y1 - y0) * 0.02)
                x0 = max(0, x0 - margin_x)
                y0 = max(0, y0 - margin_y)
                x1 = min(render_w, x1 + margin_x)
                y1 = min(render_h, y1 + margin_y)

                crop = page_image.crop((x0, y0, x1, y1)).convert("RGB")

                w, h = crop.size
                min_side = min(w, h)
                if min_side < MIN_SHORT_SIDE and min_side > 0:
                    factor = math.ceil(MIN_SHORT_SIDE / min_side)
                    crop = crop.resize((w * factor, h * factor), resample=Image.LANCZOS)

                out_path = images_dir / f"{pdf_stem}_{page_index}_figure_{idx}.png"
                crop.save(out_path)
                count += 1
    return count


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not any(OUTPUT_DIR.glob("res_*.json")):
        run_layout_detection(PDF_PATH, OUTPUT_DIR)
    else:
        print("检测到已有 res_*.json，跳过版面检测。")
    extract_text(PDF_PATH, TEXT_PATH)
    image_count = extract_layout_images(PDF_PATH, OUTPUT_DIR, IMAGES_DIR)
    print(f"Text saved to: {TEXT_PATH}")
    print(f"Images saved to: {IMAGES_DIR} (count={image_count})")


if __name__ == "__main__":
    main()
