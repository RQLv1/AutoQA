#!/usr/bin/env python3
"""
仅测试图片组合功能（不运行布局检测）
使用 assemble.py 中的默认 PDF 配置
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf2txt.assemble import PDF_PATH, OUTPUT_DIR, IMAGES_DIR, TARGET_LABELS, assemble_elements_from_res

def main():
    """主测试函数"""
    print("=" * 80)
    print("PDF 图片组合测试（使用 assemble.py 默认配置）")
    print("=" * 80)

    print(f"\nPDF 文件: {PDF_PATH.name}")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"图片保存目录: {IMAGES_DIR}")

    # 检查 PDF 文件是否存在
    if not PDF_PATH.exists():
        print(f"\n✗ 错误: PDF文件不存在")
        print(f"路径: {PDF_PATH}")
        return

    # 检查输出目录是否存在
    if not OUTPUT_DIR.exists():
        print(f"\n✗ 错误: 输出目录不存在")
        print(f"路径: {OUTPUT_DIR}")
        print("\n提示: 请先运行 pdf2txt.py 生成 res_*.json 文件")
        return

    # 检查是否有 res_*.json 文件
    res_files = list(OUTPUT_DIR.glob("res_*.json"))
    if not res_files:
        print(f"\n✗ 错误: 未找到 res_*.json 文件")
        print(f"目录: {OUTPUT_DIR}")
        print("\n提示: 请先运行 pdf2txt.py 生成布局检测结果")
        return

    print(f"\n✓ 找到 {len(res_files)} 个 res_*.json 文件")
    print(f"目标元素类型: {', '.join(sorted(TARGET_LABELS))}")

    # 清理旧的组合图片（如果有）
    if IMAGES_DIR.exists():
        old_images = list(IMAGES_DIR.glob("*_assembled.png"))
        if old_images:
            print(f"\n清理 {len(old_images)} 个旧的组合图片...")
            for img in old_images:
                img.unlink()

    # 运行图片组合
    print("\n" + "=" * 80)
    print("开始处理...")
    print("=" * 80 + "\n")

    try:
        count = assemble_elements_from_res(
            pdf_path=PDF_PATH,
            layout_dir=OUTPUT_DIR,
            images_dir=IMAGES_DIR,
            target_labels=TARGET_LABELS
        )

        print("\n" + "=" * 80)
        print("处理完成！")
        print("=" * 80)

        if count > 0:
            print(f"\n✓ 成功生成 {count} 张组合图片")
            print(f"保存位置: {IMAGES_DIR}\n")
            print("生成的图片:")
            for img_file in sorted(IMAGES_DIR.glob("*_assembled.png")):
                file_size = img_file.stat().st_size / 1024  # KB
                print(f"  - {img_file.name} ({file_size:.1f} KB)")
        else:
            print(f"\n⚠ 未生成任何图片")
            print("\n可能的原因:")
            print("  1. res_*.json 中没有 image/chart/figure_title 类型的元素")
            print("  2. 所有图片都被过滤器过滤掉了（尺寸太小、空白太多等）")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
