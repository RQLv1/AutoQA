### 图片大面积空白解决方案

### 1.计算“最小包围盒”并裁剪

我们需要修改 `assemble_page_elements` 函数。在粘贴完所有元素后，计算这些元素的 **并集包围盒（Union Bounding Box）** ，然后将画布裁剪到这个范围。

请修改 `rqlv1/autoqa/AutoQA-rqlv/pdf2txt/assemble.py` 中的该函数：

**Python**

```
def assemble_page_elements(
    elements: list[tuple[Image.Image, tuple[int, int, int, int], str]],
    render_size: tuple[int, int]
) -> Image.Image:
    """
    将裁剪的元素按原始位置组合，并裁剪出最小包含区域。
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
```

### 2.图片过滤解决方案

### 修改代码方案

建议在 `pdf2txt` 目录下创建一个新的工具文件 `image_filter.py`，然后在 `assemble.py` 中调用它。模型采用"gemini3-flash"

#### 第一步：创建过滤工具 `pdf2txt/image_filter.py`

在 `rqlv1/autoqa/AutoQA-rqlv/pdf2txt/` 下新建 `image_filter.py`，写入以下代码。这包含规则过滤和大模型过滤两种实现。

**Python**

```
import numpy as np
from PIL import Image
import math
import base64
import os
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
            # 认为大于240的像素点是“白色”背景
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

def llm_check_image_validity(image_path, api_key, model="gpt-4o"):
    """
    使用大模型 Vision 能力判断图片是否有效。
    需要设置 OPENAI_API_KEY 环境变量或传入 api_key。
    """
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
        return True # 如果LLM失败，默认保留以免误删
```

#### 第二步：集成到 `assemble.py`

找到你的 rqlv1/autoqa/AutoQA-rqlv/pdf2txt/assemble.py。

在文件顶部导入：

**Python**

```
import os
# 假设 image_filter.py 在同一目录下
from .image_filter import is_junk_image, llm_check_image_validity 
```

找到保存图片的地方（通常是一个循环，最后调用 `image.save(...)` 或 `cv2.imwrite(...)`）。在保存 **之后** 或者保存 **之前** 加入检查。

建议的集成逻辑如下：

**Python**

```
# 假设 img_path 是你刚刚生成的图片路径
# ... 图片保存代码 ...
image.save(img_path) 

# === 新增过滤逻辑 ===
is_junk, reason = is_junk_image(img_path)

if is_junk:
    print(f"Removing junk image {img_path}: {reason}")
    os.remove(img_path) # 删除无效图片
    # 并且可以在这里从你的最终数据列表中移除该条目
else:
    # (可选) 如果规则检查通过，但你想更严格，可以开启 LLM 检查
    # 注意：这会增加成本和时间
    # api_key = os.getenv("OPENAI_API_KEY")
    # if api_key and not llm_check_image_validity(img_path, api_key):
    #     print(f"LLM rejected image {img_path}")
    #     os.remove(img_path)
    pass
# ===================
```

### 推荐参数设置

对于你的需求（过滤 "Check for updates" 和空白 Caption）：

* **`min_size=(150, 150)`** : 很多 logo 或 header 都在 100px 以下。
* **`max_white_ratio=0.92`** : 科学图表通常有较多内容，如果超过 92% 都是白色，大概率是只有一行 Caption 的截图。
* **`min_entropy=3.0`** : "Check for updates" 这种图标颜色单一，熵值很低。复杂的电镜图或曲线图熵值通常 > 5.0。
