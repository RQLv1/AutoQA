#!/usr/bin/env python3
"""
完整的PDF处理测试流程：
1. 运行布局检测（生成 res_*.json）
2. 组合图片元素（应用新的过滤和裁剪功能）
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf2txt.pdf2txt import run_layout_detection
from pdf2txt.assemble import assemble_elements_from_res, TARGET_LABELS

# 测试用的PDF路径
TEST_PDF = Path(__file__).resolve().parent / "data" / "pdf" / \
           "Adv Funct Materials - 2025 - Tian - Rb Doping and Lattice Strain " \
           "Synergistically Engineering Oxygen Vacancies in TiO2 for.pdf"
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / TEST_PDF.stem
IMAGES_DIR = OUTPUT_DIR / "images"


def main():
    """主测试函数"""
    print("=" * 80)
    print("PDF 处理完整测试流程")
    print("=" * 80)

    if not TEST_PDF.exists():
        print(f"\n错误: 测试PDF文件不存在")
        print(f"路径: {TEST_PDF}")
        return

    print(f"\n测试PDF: {TEST_PDF.name}")
    print(f"输出目录: {OUTPUT_DIR}")

    # 步骤1: 检查是否已有 res_*.json 文件
    res_files = list(OUTPUT_DIR.glob("res_*.json")) if OUTPUT_DIR.exists() else []

    if not res_files:
        print("\n" + "=" * 80)
        print("步骤 1: 运行布局检测 (生成 res_*.json)")
        print("=" * 80)
        print("\n注意: 这一步需要 PaddleOCR 模型，可能需要一些时间...")
        print("如果出错，请确保已安装: pip install paddleocr paddlepaddle")

        try:
            run_layout_detection(TEST_PDF, OUTPUT_DIR)
            print("\n✓ 布局检测完成")
        except Exception as e:
            print(f"\n✗ 布局检测失败: {e}")
            print("\n提示: 如果遇到模型下载问题，可能需要手动下载模型")
            return
    else:
        print(f"\n✓ 已存在 {len(res_files)} 个 res_*.json 文件，跳过布局检测")

    # 步骤2: 组合图片元素
    print("\n" + "=" * 80)
    print("步骤 2: 组合图片元素 (应用过滤和裁剪)")
    print("=" * 80)
    print(f"\n目标元素类型: {', '.join(sorted(TARGET_LABELS))}")
    print("\n处理中...")

    try:
        count = assemble_elements_from_res(
            pdf_path=TEST_PDF,
            layout_dir=OUTPUT_DIR,
            images_dir=IMAGES_DIR,
            target_labels=TARGET_LABELS
        )

        print("\n" + "=" * 80)
        print("测试完成！")
        print("=" * 80)
        print(f"\n成功生成 {count} 张组合图片")

        if count > 0:
            print(f"保存位置: {IMAGES_DIR}")
            print("\n生成的图片列表:")
            for img_file in sorted(IMAGES_DIR.glob("*_assembled.png")):
                file_size = img_file.stat().st_size / 1024  # KB
                print(f"  - {img_file.name} ({file_size:.1f} KB)")
        else:
            print("\n提示: 未生成图片，可能是因为:")
            print("  1. PDF中没有符合条件的元素")
            print("  2. 所有图片都被过滤器过滤掉了")
            print("  3. res_*.json 文件中没有 image/chart/figure_title 类型的元素")

    except Exception as e:
        print(f"\n✗ 图片组合失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
