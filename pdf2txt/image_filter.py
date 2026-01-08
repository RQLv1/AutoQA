import numpy as np
from PIL import Image
import math
import base64
import os
import sys
from pathlib import Path

# 添加父目录到路径以便导入配置
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.config import MODEL_SOLVE_MEDIUM

import requests

# === 1. 规则过滤 (快速、免费) ===

def get_image_entropy(img_pil):
    """计算图片香农熵 (衡量信息丰富度)"""
    # 转换为灰度
    img_gray = img_pil.convert('L')
    histogram = img_gray.histogram()
    histogram_length = sum(histogram)
    samples_probability = [float(h) / histogram_length for h in histogram]
    return -sum([p * math.log(p, 2) for p in samples_probability if p != 0])

def is_junk_image(image_path, min_size=(100, 100), max_white_ratio=0.95, min_entropy=3.5):
    """
    判断是否为垃圾图片
    :param image_path: 图片路径
    :param min_size: 最小宽/高 (过滤图标)
    :param max_white_ratio: 最大空白比例 (过滤只有Caption或空白图)
    :param min_entropy: 最小信息熵 (过滤简单图形)
    :return: (True/False, reason)
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # 1. 尺寸过滤 (过滤 Check for updates 等小图标)
            if width < min_size[0] or height < min_size[1]:
                return True, f"Too small: {width}x{height}"

            # 2. 长宽比过滤 (过滤极细长的分割线)
            aspect_ratio = width / height
            if aspect_ratio > 10 or aspect_ratio < 0.1:
                return True, f"Extreme aspect ratio: {aspect_ratio:.2f}"

            # 3. 空白占比过滤
            img_gray = img.convert('L')
            np_img = np.array(img_gray)
            # 认为大于240的像素点是"白色"背景
            white_pixels = np.sum(np_img > 240)
            total_pixels = np_img.size
            white_ratio = white_pixels / total_pixels

            if white_ratio > max_white_ratio:
                return True, f"Too much whitespace: {white_ratio:.2%}"

            # 4. 信息熵过滤 (可选，针对只有少量文字的空白图)
            # 复杂的科学图表通常 entropy > 4.5
            entropy = get_image_entropy(img)
            if entropy < min_entropy:
                return True, f"Low entropy (simple image): {entropy:.2f}"

            return False, "Pass"
    except Exception as e:
        print(f"Error checking image {image_path}: {e}")
        return True, "Error reading file"

# === 2. 大模型过滤 (精准、成本高) ===

def llm_check_image_validity(image_path, api_key, model=None):
    """
    使用大模型 Vision 能力判断图片是否有效。
    默认使用配置文件中的 MODEL_SOLVE_MEDIUM (gemini-3-flash-preview)。
    需要设置 API_KEY 环境变量或传入 api_key。
    """
    if model is None:
        model = MODEL_SOLVE_MEDIUM
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    base64_image = encode_image(image_path)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a scientific image filter. You determine if an image extracted from a PDF is a valid, useful scientific figure (charts, diagrams, microscopy, molecules). Returns JSON: {'valid': bool, 'reason': str}."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Is this a valid scientific figure? Reject if it is just text captions, a logo (like 'Check for updates'), a page header/footer, or almost blank."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 100
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        result = response.json()
        content = result['choices'][0]['message']['content']
        # 简单解析返回结果
        if "true" in content.lower() or "yes" in content.lower():
            return True
        return False
    except Exception as e:
        print(f"LLM Check Failed: {e}")
        return True  # 如果LLM失败，默认保留以免误删
