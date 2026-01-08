#!/usr/bin/env python3
"""
简单测试脚本：直接运行 assemble.py 的 main 函数
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 直接导入并运行 assemble.py 的 main 函数
from pdf2txt.assemble import main

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("运行 PDF 元素组合测试 (使用 assemble.py 中的默认配置)")
    print("=" * 80 + "\n")

    # 运行 main 函数
    main()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
