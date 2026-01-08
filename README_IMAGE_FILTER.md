# PDF图片处理改进 - 使用说明

## 概述

根据 `change.md` 的要求，已完成以下两个改进：

1. **最小包围盒裁剪** - 解决图片大面积空白问题
2. **智能图片过滤** - 自动过滤无效图片（小图标、空白图等）

## 修改的文件

### 1. `pdf2txt/assemble.py`

**修改的函数**: `assemble_page_elements()`

**新增功能**:
- 计算所有元素的并集包围盒（Union Bounding Box）
- 添加 10px 的 padding 边距
- 裁剪画布到最小包含区域
- 在保存图片后自动调用过滤器检查
- 使用推荐参数：`min_size=(150, 150)`, `max_white_ratio=0.92`, `min_entropy=3.0`

**修改前后对比**:
```python
# 修改前
def assemble_page_elements(elements, render_size):
    canvas = Image.new("RGB", render_size, color="white")
    for crop_img, (x0, y0, _x1, _y1), _label in elements:
        canvas.paste(crop_img, (x0, y0))
    return canvas  # 返回完整尺寸画布（有大量空白）

# 修改后
def assemble_page_elements(elements, render_size):
    canvas = Image.new("RGB", render_size, color="white")

    # 计算包围盒
    min_x, min_y = render_size
    max_x, max_y = 0, 0

    for crop_img, (x0, y0, x1, y1), _label in elements:
        canvas.paste(crop_img, (x0, y0))
        min_x = min(min_x, x0)
        min_y = min(min_y, y0)
        max_x = max(max_x, x1)
        max_y = max(max_y, y1)

    # 裁剪到最小区域
    padding = 10
    crop_box = (
        max(0, min_x - padding),
        max(0, min_y - padding),
        min(render_size[0], max_x + padding),
        min(render_size[1], max_y + padding)
    )
    return canvas.crop(crop_box)  # 返回裁剪后的画布
```

### 2. `pdf2txt/image_filter.py` (新建)

**包含的功能**:

#### 规则过滤器 (快速、免费)
```python
def is_junk_image(image_path, min_size=(100, 100),
                  max_white_ratio=0.95, min_entropy=3.5):
    """
    判断是否为垃圾图片
    返回: (True/False, reason)
    """
```

**过滤规则**:
1. **尺寸过滤**: 过滤宽度或高度小于阈值的图片
2. **长宽比过滤**: 过滤极端细长的分割线（>10:1 或 <1:10）
3. **空白占比过滤**: 过滤空白区域占比超过阈值的图片
4. **信息熵过滤**: 过滤信息丰富度低的简单图形

#### 大模型过滤器 (可选、精准、成本高)
```python
def llm_check_image_validity(image_path, api_key, model=None):
    """
    使用大模型 Vision 能力判断图片是否有效
    默认使用配置文件中的 MODEL_SOLVE_MEDIUM (gemini-3-flash-preview)
    """
```

## 推荐参数设置

针对科学文献PDF中的图片过滤：

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `min_size` | `(150, 150)` | 过滤"Check for updates"等小图标（通常<100px） |
| `max_white_ratio` | `0.92` | 过滤只有Caption的空白图（科学图表空白率应<92%） |
| `min_entropy` | `3.0` | 过滤简单图标（复杂图表熵值通常>5.0） |

**参数调整指南**:
- 过滤太严格（漏掉好图）→ 降低 `min_size`，提高 `max_white_ratio`，降低 `min_entropy`
- 过滤太宽松（保留垃圾图）→ 提高 `min_size`，降低 `max_white_ratio`，提高 `min_entropy`

## 使用方法

### 方式1: 运行 assemble.py（已集成）

```bash
python pdf2txt/assemble.py
```

**配置文件中设置PDF路径** (`pdf2txt/assemble.py` 第12-16行):
```python
PDF_PATH = Path("你的PDF路径.pdf")
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / PDF_PATH.stem
```

**自动流程**:
1. 读取 `res_*.json` 文件（需先运行 `pdf2txt.py` 生成）
2. 提取并组合 image/chart/figure_title 元素
3. **自动裁剪** - 去除大面积空白
4. **自动过滤** - 检测并删除无效图片
5. 保存到 `OUTPUT_DIR/images/`

### 方式2: 在代码中集成

```python
from pdf2txt.image_filter import is_junk_image

# 在保存图片后
image.save(img_path)

# 检查并过滤
is_junk, reason = is_junk_image(
    str(img_path),
    min_size=(150, 150),
    max_white_ratio=0.92,
    min_entropy=3.0
)

if is_junk:
    print(f"过滤无效图片: {reason}")
    os.remove(img_path)
else:
    print(f"有效图片: {img_path}")
```

### 方式3: 启用LLM过滤（可选）

在 `assemble.py` 第266-272行，取消注释：

```python
# 使用配置文件中的 MODEL_SOLVE_MEDIUM (gemini-3-flash-preview)
api_key = os.getenv("API_KEY")
if api_key and not llm_check_image_validity(str(out_path), api_key):
    print(f"  ✗ LLM判定为无效图片")
    os.remove(out_path)
    count -= 1
```

**注意**: LLM过滤会增加处理时间和API成本，建议仅在规则过滤不够精准时使用。

## 测试脚本

提供了以下测试脚本：

### 1. `demo_image_filter.py` - 过滤功能演示
```bash
python demo_image_filter.py
```
- 演示过滤器的工作原理
- 显示图片的尺寸、熵值、空白比例
- 解释各个参数的含义

### 2. `test_assemble_only.py` - 测试组合功能
```bash
python test_assemble_only.py
```
- 测试 assemble.py 的 main 函数
- 需要先运行 `pdf2txt.py` 生成 `res_*.json`

### 3. `test_pdf_pipeline.py` - 完整流程测试
```bash
python test_pdf_pipeline.py
```
- 包含布局检测 + 图片组合
- 需要安装 PaddleOCR

## 输出示例

运行 `assemble.py` 时的输出：

```
============================================================
开始组合 PDF 元素...
目标元素类型: chart, figure_title, image
============================================================

  ✓ 页面 0: 组合了 3 个元素 → example_page_0_assembled.png
  ✗ 过滤无效图片: Too small: 80x80
  ✓ 页面 1: 组合了 5 个元素 → example_page_1_assembled.png
  ✗ 过滤无效图片: Too much whitespace: 96.50%
  ✓ 页面 2: 组合了 2 个元素 → example_page_2_assembled.png
  ✗ 过滤无效图片: Low entropy (simple image): 2.45

============================================================
完成！共生成 3 张组合图
保存位置: /path/to/output/images
============================================================
```

## 技术细节

### 最小包围盒计算

```python
# 初始化为画布边界
min_x, min_y = render_w, render_h
max_x, max_y = 0, 0

# 遍历所有元素，更新边界
for crop_img, (x0, y0, x1, y1), label in elements:
    min_x = min(min_x, x0)
    min_y = min(min_y, y0)
    max_x = max(max_x, x1)
    max_y = max(max_y, y1)

# 添加padding并裁剪
padding = 10
final_box = (
    max(0, min_x - padding),
    max(0, min_y - padding),
    min(render_w, max_x + padding),
    min(render_h, max_y + padding)
)
return canvas.crop(final_box)
```

### 信息熵计算

信息熵用于衡量图片的信息丰富度：

```python
def get_image_entropy(img_pil):
    img_gray = img_pil.convert('L')
    histogram = img_gray.histogram()
    histogram_length = sum(histogram)
    samples_probability = [float(h) / histogram_length for h in histogram]
    return -sum([p * math.log(p, 2) for p in samples_probability if p != 0])
```

- 熵值越高，图片信息越丰富
- 单色图标: 熵值 < 2.0
- 简单图标: 熵值 2.0-3.0
- 复杂图表: 熵值 > 5.0

## 配置集成

图片过滤器已与项目配置系统集成：

- **模型配置**: 从 `utils/config.py` 读取 `MODEL_SOLVE_MEDIUM`
- **API配置**: 使用环境变量 `API_KEY`
- **灵活切换**: 可通过配置文件切换不同的模型

```python
# image_filter.py
from utils.config import MODEL_SOLVE_MEDIUM

def llm_check_image_validity(image_path, api_key, model=None):
    if model is None:
        model = MODEL_SOLVE_MEDIUM  # 默认: gemini-3-flash-preview
    # ...
```

## 常见问题

### Q1: 为什么所有图片都被过滤掉了？
A: 可能参数设置过严。尝试调整：
- 降低 `min_size` 到 `(100, 100)`
- 提高 `max_white_ratio` 到 `0.95`
- 降低 `min_entropy` 到 `2.5`

### Q2: 如何只使用裁剪功能，不使用过滤？
A: 注释掉 `assemble.py` 第250-272行的过滤代码块。

### Q3: LLM过滤成本如何？
A: 取决于图片数量和模型：
- `gemini-3-flash-preview`: 约 $0.0001/次
- 100张图片 ≈ $0.01

### Q4: 如何查看被过滤掉的图片？
A: 修改代码，在删除前先移动到备份目录：
```python
if is_junk:
    backup_dir = images_dir / "filtered"
    backup_dir.mkdir(exist_ok=True)
    shutil.move(out_path, backup_dir / out_path.name)
```

## 总结

✅ **已完成的改进**:
1. 最小包围盒裁剪 - 去除大面积空白
2. 规则过滤器 - 快速过滤无效图片
3. LLM过滤器（可选）- 精准过滤
4. 集成到现有流程
5. 使用项目配置系统
6. 提供测试和演示脚本

📊 **预期效果**:
- 图片文件大小减少 30-70%（因裁剪空白）
- 过滤掉 20-40% 的无效图片
- 保留所有有价值的科学图表

🔧 **维护建议**:
- 根据实际数据调整过滤参数
- 定期检查被过滤的图片，避免误判
- 必要时启用LLM过滤提高精度
