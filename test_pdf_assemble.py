#!/usr/bin/env python3
"""
测试脚本：处理第一个PDF文件，提取并组合图片元素
"""
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf2txt.assemble import assemble_elements_from_res, TARGET_LABELS

# 配置路径
DATA_PDF_DIR = Path(__file__).resolve().parent / "data" / "pdf"
OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "output"

def main():
    """测试主函数"""
    print("=" * 80)
    print("PDF 图片元素组合测试")
    print("=" * 80)

    # 查找已处理的PDF（output目录中有res_*.json的）
    pdf_path = None
    output_dir = None

    # 遍历output目录，找到第一个有res_*.json的文件夹
    if OUTPUT_BASE_DIR.exists():
        for subdir in sorted(OUTPUT_BASE_DIR.iterdir()):
            if subdir.is_dir():
                res_files = list(subdir.glob("res_*.json"))
                if res_files:
                    # 找到对应的PDF文件
                    potential_pdf = DATA_PDF_DIR / f"{subdir.name}.pdf"
                    if potential_pdf.exists():
                        pdf_path = potential_pdf
                        output_dir = subdir
                        print(f"\n找到已处理的PDF: {pdf_path.name}")
                        print(f"对应的输出目录: {output_dir}")
                        break

    if pdf_path is None:
        print(f"\n错误: 未找到已处理的PDF文件")
        print(f"请先运行 PDF 布局检测，生成 res_*.json 文件")
        print(f"\n可用的PDF文件:")
        for pdf in sorted(DATA_PDF_DIR.glob("*.pdf"))[:5]:
            print(f"  - {pdf.name}")
        return

    print(f"完整路径: {pdf_path}")

    # 设置输出目录
    layout_dir = output_dir  # res_*.json 文件应该在这里
    images_dir = output_dir / "images"

    print(f"\n布局文件目录: {layout_dir}")
    print(f"图片保存目录: {images_dir}")

    # 检查是否存在 res_*.json 文件
    res_files = list(layout_dir.glob("res_*.json"))
    print(f"\n找到 {len(res_files)} 个 res_*.json 文件")

    # 显示目标元素类型
    print(f"\n目标元素类型: {', '.join(sorted(TARGET_LABELS))}")

    # 执行元素组合
    print("\n" + "=" * 80)
    print("开始处理...")
    print("=" * 80)

    count = assemble_elements_from_res(
        pdf_path=pdf_path,
        layout_dir=layout_dir,
        images_dir=images_dir,
        target_labels=TARGET_LABELS
    )

    print("\n" + "=" * 80)
    print(f"处理完成！")
    print(f"成功生成 {count} 张组合图片")
    if count > 0:
        print(f"图片保存位置: {images_dir}")
        print("\n生成的图片:")
        for img_file in sorted(images_dir.glob("*_assembled.png")):
            print(f"  - {img_file.name}")
    print("=" * 80)

if __name__ == "__main__":
    main()
