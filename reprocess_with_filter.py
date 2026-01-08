#!/usr/bin/env python3
"""
重新处理已有的PDF，应用新的裁剪和过滤功能
"""
import sys
import shutil
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf2txt.assemble import assemble_elements_from_res, TARGET_LABELS

OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "output"
DATA_PDF_DIR = Path(__file__).resolve().parent / "data" / "pdf"


def find_processed_pdfs():
    """查找已处理的PDF（有res_*.json的）"""
    processed = []
    if OUTPUT_BASE_DIR.exists():
        for subdir in sorted(OUTPUT_BASE_DIR.iterdir()):
            if subdir.is_dir():
                res_files = list(subdir.glob("res_*.json"))
                if res_files:
                    # 找到对应的PDF文件
                    potential_pdf = DATA_PDF_DIR / f"{subdir.name}.pdf"
                    if potential_pdf.exists():
                        processed.append((potential_pdf, subdir))
    return processed


def main():
    """主函数"""
    print("=" * 80)
    print("重新处理PDF - 应用新的裁剪和过滤功能")
    print("=" * 80)

    # 查找已处理的PDF
    processed_pdfs = find_processed_pdfs()

    if not processed_pdfs:
        print("\n未找到已处理的PDF")
        print("提示: 需要先运行 pdf2txt.py 生成 res_*.json 文件")
        return

    print(f"\n找到 {len(processed_pdfs)} 个已处理的PDF\n")

    # 选择要处理的PDF（前3个）
    to_process = processed_pdfs[:3]

    print("将处理以下PDF:")
    for i, (pdf_path, output_dir) in enumerate(to_process, 1):
        res_count = len(list(output_dir.glob("res_*.json")))
        print(f"  {i}. {pdf_path.name[:60]}...")
        print(f"     输出目录: {output_dir.name[:60]}...")
        print(f"     res_*.json 文件数: {res_count}")

    print("\n" + "=" * 80)

    total_before = 0
    total_after = 0

    for idx, (pdf_path, output_dir) in enumerate(to_process, 1):
        print(f"\n处理 {idx}/{len(to_process)}: {pdf_path.name[:50]}...")
        print("-" * 80)

        images_dir = output_dir / "images"

        # 统计旧图片数量
        old_images = list(images_dir.glob("*_assembled.png")) if images_dir.exists() else []
        old_count = len(old_images)
        total_before += old_count

        if old_count > 0:
            print(f"旧图片数量: {old_count}")
            # 备份旧图片
            backup_dir = output_dir / "images_backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            if images_dir.exists():
                shutil.copytree(images_dir, backup_dir)
                print(f"✓ 已备份到: {backup_dir.name}/")

            # 删除旧图片
            for img in old_images:
                img.unlink()

        # 重新处理
        try:
            count = assemble_elements_from_res(
                pdf_path=pdf_path,
                layout_dir=output_dir,
                images_dir=images_dir,
                target_labels=TARGET_LABELS
            )
            total_after += count

            print(f"\n新图片数量: {count}")
            if old_count > 0:
                diff = count - old_count
                if diff < 0:
                    print(f"过滤掉: {abs(diff)} 张 ({abs(diff)/old_count*100:.1f}%)")
                elif diff > 0:
                    print(f"增加: {diff} 张")
                else:
                    print("数量相同")

        except Exception as e:
            print(f"✗ 处理失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("处理完成汇总")
    print("=" * 80)
    print(f"处理PDF数量: {len(to_process)}")
    print(f"处理前总图片: {total_before}")
    print(f"处理后总图片: {total_after}")
    if total_before > 0:
        filtered = total_before - total_after
        print(f"过滤掉: {filtered} 张 ({filtered/total_before*100:.1f}%)")
    print("\n功能说明:")
    print("  1. ✓ 最小包围盒裁剪 - 去除大面积空白")
    print("  2. ✓ 规则过滤 - 过滤小图标、空白图、简单图形")
    print("  3. 旧图片已备份到各自的 images_backup/ 目录")
    print("=" * 80)


if __name__ == "__main__":
    main()
