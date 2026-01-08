#!/usr/bin/env python3
"""
演示图片过滤功能的使用方法
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf2txt.image_filter import is_junk_image, get_image_entropy
from PIL import Image
import numpy as np


def demo_filter_functionality():
    """演示过滤功能"""
    print("=" * 80)
    print("图片过滤功能演示")
    print("=" * 80)

    # 查找一些测试图片
    output_base = Path(__file__).resolve().parent / "output"
    test_images = []

    # 查找所有图片文件
    if output_base.exists():
        for img_dir in output_base.glob("*/images"):
            test_images.extend(list(img_dir.glob("*.png"))[:3])

    if not test_images:
        print("\n未找到测试图片")
        print("创建示例图片进行演示...\n")

        # 创建临时测试图片
        temp_dir = Path(__file__).resolve().parent / "temp_test"
        temp_dir.mkdir(exist_ok=True)

        # 1. 小图片 (应该被过滤)
        small_img = Image.new('RGB', (80, 80), color='white')
        small_path = temp_dir / "small_icon.png"
        small_img.save(small_path)
        test_images.append(small_path)

        # 2. 空白图片 (应该被过滤)
        blank_img = Image.new('RGB', (500, 300), color='white')
        # 添加一点文字模拟caption
        blank_path = temp_dir / "blank_with_caption.png"
        blank_img.save(blank_path)
        test_images.append(blank_path)

        # 3. 有内容的图片 (应该通过)
        content_img = Image.new('RGB', (500, 400), color='white')
        # 添加一些随机内容
        pixels = np.array(content_img)
        pixels[50:350, 50:450] = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
        content_img = Image.fromarray(pixels)
        content_path = temp_dir / "scientific_figure.png"
        content_img.save(content_path)
        test_images.append(content_path)

        print(f"✓ 创建了 {len(test_images)} 个测试图片\n")

    # 测试每个图片
    print("\n测试图片过滤 (使用推荐参数):")
    print("-" * 80)

    passed = 0
    filtered = 0

    for img_path in test_images[:5]:  # 限制最多5张
        print(f"\n图片: {img_path.name}")

        try:
            # 获取图片信息
            with Image.open(img_path) as img:
                width, height = img.size
                print(f"  尺寸: {width} x {height}")

                # 计算熵值
                entropy = get_image_entropy(img)
                print(f"  信息熵: {entropy:.2f}")

                # 计算空白比例
                img_gray = img.convert('L')
                np_img = np.array(img_gray)
                white_pixels = np.sum(np_img > 240)
                total_pixels = np_img.size
                white_ratio = white_pixels / total_pixels
                print(f"  空白比例: {white_ratio:.2%}")

            # 应用过滤器 (使用推荐参数)
            is_junk, reason = is_junk_image(
                str(img_path),
                min_size=(150, 150),
                max_white_ratio=0.92,
                min_entropy=3.0
            )

            if is_junk:
                print(f"  结果: ✗ 过滤 - {reason}")
                filtered += 1
            else:
                print(f"  结果: ✓ 通过")
                passed += 1

        except Exception as e:
            print(f"  错误: {e}")

    print("\n" + "=" * 80)
    print(f"测试完成: {passed} 张通过, {filtered} 张被过滤")
    print("=" * 80)

    # 清理临时文件
    temp_dir = Path(__file__).resolve().parent / "temp_test"
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir)
        print("\n✓ 已清理临时测试文件")


def demo_parameter_explanation():
    """解释过滤参数"""
    print("\n\n" + "=" * 80)
    print("过滤参数说明")
    print("=" * 80)

    print("""
推荐参数设置 (针对科学文献图片):

1. min_size=(150, 150)
   - 过滤宽度或高度小于150像素的图片
   - 目的: 去除小图标、按钮、logo等（如"Check for updates"）

2. max_white_ratio=0.92
   - 过滤空白占比超过92%的图片
   - 目的: 去除只有Caption文字、几乎空白的截图
   - 科学图表通常有较多内容，空白率应低于92%

3. min_entropy=3.0
   - 过滤信息熵低于3.0的图片
   - 目的: 去除颜色单一、内容简单的图标
   - 复杂的科学图表（电镜图、曲线图等）熵值通常 > 5.0

参数调整建议:
- 如果过滤太严格（漏掉好图）: 降低 min_size, 提高 max_white_ratio, 降低 min_entropy
- 如果过滤太宽松（保留垃圾图）: 提高 min_size, 降低 max_white_ratio, 提高 min_entropy
    """)


if __name__ == "__main__":
    demo_filter_functionality()
    demo_parameter_explanation()

    print("\n\n使用方法:")
    print("-" * 80)
    print("""
在你的代码中集成图片过滤:

    from pdf2txt.image_filter import is_junk_image

    # 在保存图片后
    image.save(img_path)

    # 检查是否为垃圾图片
    is_junk, reason = is_junk_image(
        img_path,
        min_size=(150, 150),
        max_white_ratio=0.92,
        min_entropy=3.0
    )

    if is_junk:
        print(f"过滤: {reason}")
        os.remove(img_path)  # 删除垃圾图片
    else:
        print("有效图片，保留")
    """)
    print("=" * 80)
