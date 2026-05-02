# Frontend 模块文档

> 本文档记录 `frontend/` 目录下每个文件的作用、设计理念和使用方法，供日后回顾。

---

## 模块定位

`frontend/` 是 Agent 的**"耳朵"和"嘴巴"**。

| 角色 | 说明 |
|------|------|
| **耳朵** | 听音频文件，理解内容 |
| **嘴巴** | 在流程末尾，结合所有证据，生成最终答案 |

**和人类的比喻**：Frontend 就像一个会听会说的专家。你给他一段录音，他告诉你里面说了什么。等到最后总结时，他结合所有信息给出精确答案。

---

## 文件逐一说明

### 1. `base.py` — 抽象基类

**作用**：定义所有前端必须实现的接口。

**核心内容**：
```python
class BaseFrontend(ABC):
    @abstractmethod
    def name(self) -> str: ...           # 前端名称
    @abstractmethod  
    def run(self, question, audio_path, question_oriented_prompt) -> FrontendOutput: ...  # 初始描述
    def generate_final_answer(self, question, audio_path, context) -> str: ...  # 最终答案
    def validate_inputs(self, question, audio_path) -> None: ...  # 输入校验
```

**为什么需要抽象基类？**

想象以后你可能想换模型：
- 今天用 OpenAI 的 `gpt-4o-audio-preview`
- 明天换成通义千问的 `qwen3-omni-flash`
- 后天换成本地部署的 `Qwen2-Audio`

**无论底层怎么变，Graph 里的节点只需要调用：**
```python
frontend.run(question, audio_path)
frontend.generate_final_answer(question, audio_path, context)
```

这就是**"接口与实现分离"的设计思想**。

**使用示例**：
```python
from frontend import BaseFrontend

# 错误！不能直接实例化抽象类
frontend = BaseFrontend()  # TypeError: Can't instantiate abstract class
```

---

### 2. `openai_compatible_frontend.py` — 真实实现

**作用**：调用任意 OpenAI 兼容 API 处理音频。

**支持的服务商**：
- OpenAI 官方 (`gpt-4o-audio-preview`)
- xi-ai.cn 等第三方平台
- 阿里云 DashScope (`qwen3-omni-flash`)

**核心方法**：

#### `__init__` — 初始化
```python
frontend = OpenAICompatibleFrontend(
    model="gpt-4o-audio-preview",           # 模型名
    api_key="sk-xxxxx",                     # API Key
    base_url="https://api-2.xi-ai.cn/v1",   # API 地址
    modalities=["text", "audio"],           # 音频模型必需
    audio={"voice": "alloy", "format": "wav"},  # 音频模型必需
    max_retries=3,                          # 失败重试次数
)
```

**API Key 读取优先级：**
1. 传入的 `api_key` 参数
2. 环境变量 `OPENAI_API_KEY`
3. 环境变量 `DASHSCOPE_API_KEY`
4. 都没有 → 报错（Fail-Fast）

#### `run()` — 生成初始描述

**5 个步骤：**
```
输入校验 → 音频转 base64 → 加载 prompt → 调用 API → 包装返回值
```

**关键设计：`question_oriented_prompt`**
```python
effective_question = question_oriented_prompt or question
```
- 如果 Planner 生成了定制化 prompt（来自 `initial_prompt_node`），就用它
- 如果没有，就用用户的原始问题

#### `generate_final_answer()` — 生成最终答案

和 `run()` 的区别：

| | `run()` | `generate_final_answer()` |
|--|---------|--------------------------|
| **调用时机** | 流程**开头** | 流程**结尾** |
| **输入** | 问题 + 音频 | 问题 + 音频 + **所有证据** |
| **prompt 内容** | 简单分析指令 | 包含 evidence_summary、initial_plan 等 |
| **输出** | 初始 caption | **最终答案** |

#### 私有方法

| 方法 | 作用 |
|------|------|
| `_encode_audio()` | 读取音频文件 → 转成 base64 字符串 |
| `_load_prompt()` | 从 `prompts/` 目录读取 `.md` 文件 |
| `_call_api()` | 构造 OpenAI 格式请求 → 发送 → 解析返回 |
| `_get_audio_format()` | 根据文件后缀判断音频格式（wav/mp3/m4a 等） |

**关于音频传输格式**：
- HTTP 只能传输文本，不能传输二进制文件
- base64 是把二进制转成文本的标准方法
- 63KB 的 wav 文件 → 编码后约 86KB 字符

**API 调用的消息格式**：
```python
messages = [
    {"role": "system", "content": "You are an expert audio analyst..."},
    {"role": "user", "content": [
        {"type": "text", "text": "用户问题..."},
        {"type": "input_audio", "input_audio": {
            "data": "base64字符串...",
            "format": "wav"
        }}
    ]}
]
```

**API 返回格式的特殊性（针对 gpt-4o-audio-preview）：**

普通文本模型返回：
```python
response.choices[0].message.content  # ← 文本在这里
```

音频模型 `gpt-4o-audio-preview` 返回：
```python
response.choices[0].message.content           # ← None（空的）
response.choices[0].message.audio.transcript  # ← 真正的识别结果在这里
```

代码里做了兼容处理：
```python
if hasattr(msg, "audio") and msg.audio and hasattr(msg.audio, "transcript"):
    return msg.audio.transcript or ""   # 音频模型
return msg.content or ""               # 文本模型
```

---

### 3. `__init__.py` — 包入口

**作用**：让你用简洁的方式导入：
```python
from frontend import BaseFrontend, OpenAICompatibleFrontend
```

而不用记具体文件路径：
```python
from frontend.base import BaseFrontend
from frontend.openai_compatible_frontend import OpenAICompatibleFrontend
```

---

## 数据流程图

```
用户问题 + 音频路径
        |
        v
+-----------------------------------+
|         frontend.run()            |
|  1. validate_inputs()             |
|  2. _encode_audio() → base64      |
|  3. _load_prompt() → 读取 .md     |
|  4. _call_api() → 发送给 API      |
|  5. FrontendOutput(caption)       |
+-----------------------------------+
        |
        v
   返回 caption 给 Graph
```

```
最终答案阶段：
用户问题 + 音频路径 + 所有证据
        |
        v
+-----------------------------------+
|   frontend.generate_final_answer() |
|  1. 加载所有证据和计划           |
|  2. _encode_audio() → base64       |
|  3. _call_api() → 发送给 API       |
|  4. 返回最终答案字符串            |
+-----------------------------------+
        |
        v
   返回答案给 Graph
```

---

## 使用示例

### 基本使用
```python
from frontend import OpenAICompatibleFrontend

frontend = OpenAICompatibleFrontend(
    model="gpt-4o-audio-preview",
    api_key="sk-xxxxx",
    base_url="https://api-2.xi-ai.cn/v1",
)

# 生成初始描述
result = frontend.run(
    question="What is being said?",
    audio_path="D:\\audio\\test.wav",
)
print(result.question_guided_caption)

# 生成最终答案
answer = frontend.generate_final_answer(
    question="What is being said?",
    audio_path="D:\\audio\\test.wav",
    context={
        "evidence_summary": "...",
        "initial_plan": {...},
    },
)
print(answer)
```

### 使用 Planner 生成的定制化 prompt
```python
# initial_prompt_node 生成了更好的 prompt
better_prompt = "请仔细听这段音频，重点关注说话人的年龄和情绪..."

result = frontend.run(
    question="What is being said?",
    audio_path="D:\\audio\\test.wav",
    question_oriented_prompt=better_prompt,  # ← 使用定制 prompt
)
```

---

## 与原项目的区别

| 项目 | 原项目 AUDIO_AGENT | 本项目 agent-basic |
|------|------------------|-------------------|
| 前端适配器 | Qwen2-Audio、Qwen3-Omni、OpenAI、Gemini 等 5+ 个 | 只保留 OpenAICompatibleFrontend |
| 音频支持 | 多音频 `list[str]` | 单音频 `str` |
| Prompt 文件 | 有 `frontend_final_answer_system.md` 等 | 精简为最少必要 |
| 音频传输 | 多种格式（API、本地多模态） | 统一用 base64 + input_audio |
| 返回处理 | 分离在各适配器中 | 统一处理 audio.transcript |

---

## 常见问题

### Q1: 运行时提示 "No API key provided"
**原因**：没有传入 api_key，也没有设置环境变量。
**解决**：
```bash
# Windows
set OPENAI_API_KEY=sk-xxxxx

# 或者在代码中传入
frontend = OpenAICompatibleFrontend(api_key="sk-xxxxx")
```

### Q2: 返回结果里有很多重复内容
**现象**：模型一直重复"这段音频很短..."。
**原因**：`gpt-4o-audio-preview` 是预览版模型，存在"幻觉"问题。
**解决方案**：
1. 简化 System Prompt，去掉过多的结构化要求
2. 提高 temperature（从 0.3 改为 0.7）
3. 限制 max_tokens
4. 换用更稳定的模型

### Q3: 音频上传失败
**原因**：没有传 `modalities` 和 `audio` 参数。
**解决**：确保构造时传入：
```python
frontend = OpenAICompatibleFrontend(
    model="gpt-4o-audio-preview",
    modalities=["text", "audio"],
    audio={"voice": "alloy", "format": "wav"},
)
```

### Q4: 接收到的是普通文本回复，没有分析音频
**现象**："我无法访问您的本地文件..."
**原因**：API 服务商不支持 `input_audio` 消息类型。
**解决**：换用支持音频输入的服务商。

---

## 扩展指南

### 如果你想添加一个新的前端适配器

比如接入 Kimi 的音频模型：

```python
# 新建文件：frontend/kimi_frontend.py
from frontend.base import BaseFrontend
from core.schemas import FrontendOutput

class KimiFrontend(BaseFrontend):
    @property
    def name(self) -> str:
        return "kimi_audio"
    
    def run(self, question, audio_path, question_oriented_prompt=None) -> FrontendOutput:
        # 实现 Kimi 特定的调用逻辑
        caption = self._call_kimi_api(question, audio_path)
        return FrontendOutput(question_guided_caption=caption)
```

然后在 `frontend/__init__.py` 中导出：
```python
from frontend.kimi_frontend import KimiFrontend
__all__ = [..., "KimiFrontend"]
```

---

## 测试

运行前端测试：
```bash
cd agent-basic
D:\anaconda3\envs\agent-basic\python.exe tests\test_frontend.py --api-key sk-xxxxx
```
