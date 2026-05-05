# 个股预测智能体 (Individual Stock Forecast Agent)

基于 LangGraph + akshare + LLM 的 A 股个股分析预测系统。

投资核心理念：**趋势 + 主线 + 龙头**。系统通过四大因子（技术/基本面/资金/情绪）对个股进行综合评估，输出结构化的投资建议报告。

---

## 系统流程

### 完整工作流

```
START
  │
  ▼
intent_clarification          ← 解析用户意图（股票名称/代码、分析类型、时间周期、风险偏好）
  │
  ▼
market_structure              ← 分析股票在当前市场格局中的定位（主线/龙头/后排）
  │
  ▼
sector_router                 ← 动态决策：分析哪几个因子（技术/基本面/资金/情绪）
  │
  ├──► technical_analysis     ← 技术面：K线、MA、成交量、支撑阻力
  │
  ├──► fundamental_analysis   ← 基本面：PE/PB、行业、市值、估值水平
  │
  ├──► capital_analysis       ← 资金面：主力资金流向、机构持仓、融资融券
  │
  ├──► sentiment_analysis     ← 情绪面：新闻舆情、板块热度、事件催化
  │
  ▼
cross_sector_fusion           ← 综合四因子证据，输出统一评估（趋势方向/位置状态/风险等级/综合评分）
  │
  ▼
final_answer                  ← 生成结构化分析报告
  │
  ▼
END
```

### 节点说明

| 节点 | 数据来源 | LLM 作用 |
|------|---------|---------|
| intent_clarification | 用户 query | 提取股票名称、代码、分析类型、时间周期 |
| market_structure | akshare 个股信息 + K线 + 热点板块 | 判断股票在当前市场主线中的位置 |
| sector_router | 用户意图 + 市场结构 | 决策分析哪些因子（可跳过不相关因子） |
| technical_analysis | akshare 历史K线 + 代码计算MA | 定性判断技术形态和趋势 |
| fundamental_analysis | akshare 财务分析指标 + 个股信息 + 实时估值(PE/PB) | 基于 Python 计算的财报指标做定性解读 |
| capital_analysis | akshare 个股资金流向 | 判断主力资金态度 |
| sentiment_analysis | akshare 个股新闻 + 热点板块 | 评估市场情绪和舆论氛围 |
| cross_sector_fusion | 四因子 Evidence | 加权综合评分，统一投资判断 |
| final_answer | 全部证据 | 生成结构化中文报告 |

**设计特点**：每个因子节点都是"自包含"的——自己拉取 akshare 数据、代码计算基础指标、格式化文本后调用 LLM 做定性判断。所有节点都有 try-except 兜底，任何单点失败不会导致整个流程崩溃。

---

## 环境配置

### 1. 创建 Conda 环境

```bash
# 克隆已有环境（推荐，已预装所有依赖）
conda create --name stock-forecast-agent --clone agent-basic

# 或从头创建
conda create -n stock-forecast-agent python=3.11
conda activate stock-forecast-agent
pip install -r requirements.txt
```

### 2. 安装 akshare（数据获取库）

```bash
conda activate stock-forecast-agent
pip install akshare==1.18.60
```

### 3. 配置 API Key

在项目根目录创建 `.env` 文件：

```bash
copy .env.example .env
```

编辑 `.env`，填入你的 LLM API 信息：

```ini
# 必需
PLANNER_API_KEY=sk-your-api-key-here
PLANNER_BASE_URL=https://api.your-provider.com/v1

# 可选（默认 gpt-4o）
PLANNER_MODEL=gpt-4o

# 可选
MAX_STEPS=10
```

**支持的 API 格式**：任何 OpenAI-compatible 接口（如 OpenAI、Azure OpenAI、第三方代理等）。

---

## 运行方式

### 方式一：使用 .env 配置（推荐）

`.env` 中已配置好 API key 时，只需提供 `--query`：

```bash
conda activate stock-forecast-agent
python main.py --query "帮我看看贵州茅台怎么样"
```

### 方式二：命令行传入全部参数

```bash
conda activate stock-forecast-agent
python main.py \
  --query "帮我看看贵州茅台怎么样" \
  --planner-api-key sk-xxx \
  --planner-base-url https://api.xxx/v1 \
  --planner-model gpt-4o
```

### 方式三：带 Trace 运行（记录每步输入输出，方便调试）

```bash
conda activate stock-forecast-agent
python main.py --query "分析一下宁德时代" --trace
```

运行后会在当前目录生成 `trace.jsonl` 和 `trace.md` 文件。

### 不同场景的 query 示例

```bash
# 全面分析（默认四因子全开）
python main.py --query "帮我看看贵州茅台怎么样"

# 短线交易（sector_router 会自动侧重技术+资金+情绪）
python main.py --query "明天茅台能买吗"

# 长期价值（sector_router 会自动侧重基本面+技术趋势）
python main.py --query "贵州茅台值得长期持有吗"

# 风险排查
python main.py --query "宁德时代有没有暴雷风险"
```

### 输出示例

系统会输出一份结构化中文报告，包含：
- 用户意图解析
- 市场结构定位（主线/龙头判断）
- 四大因子分析（评分 + 关键发现 + 风险标记）
- 综合评估（趋势方向 / 位置状态 / 风险等级 / 综合评分）
- 证据记录

---

## 运行测试

### 全部测试

```bash
conda activate stock-forecast-agent

# Phase 1 测试（意图解析 + 市场结构 + 最终报告）
python tests/test_phase1.py

# Phase 2 测试（完整四因子流程 + 路由跳过 + akshare 数据）
python tests/test_phase2.py
```

### 测试说明

| 测试文件 | 内容 | 是否调用真实 API |
|---------|------|----------------|
| `tests/test_phase1.py` | Phase 1 完整流程 + akshare 数据获取 | ❌ 使用 MockPlanner |
| `tests/test_phase2.py` | Phase 2 完整流程 + 路由跳过测试 + akshare 数据获取 | ❌ 使用 MockPlanner |

测试使用 `MockPlanner` 模拟 LLM 响应，**不需要真实 API key**，用于验证：
- akshare 数据接口是否正常
- LangGraph 工作流节点是否正确串联
- state 传递和 schema 解析是否正确
- sector_router 的跳过/执行逻辑是否正常

---

## 项目结构

```
.
├── main.py                          # CLI 入口
├── config.py                        # 配置管理（.env + CLI 参数）
├── requirements.txt                 # Python 依赖
├── .env                             # API 配置（需手动创建）
├── .env.example                     # 配置模板
│
├── core/                            # 核心模块
│   ├── schemas.py                   # Pydantic 数据模型（UserIntent/MarketStructure/FactorEvidence/...）
│   ├── state.py                     # LangGraph AgentState 定义
│   ├── constants.py                 # 常量枚举
│   └── logging.py                   # 日志工具
│
├── graph/                           # LangGraph 工作流
│   ├── nodes.py                     # 所有节点函数（Phase 1 + Phase 2）
│   ├── builder.py                   # 图构建与编译
│   └── trace.py                     # Trace 记录工具
│
├── planner/                         # LLM 规划器
│   ├── base.py                      # 抽象基类
│   └── openai_compatible_planner.py # OpenAI-compatible 实现
│
├── prompts/                         # Prompt 模板
│   ├── intent_system.md             # 意图解析 System Prompt
│   ├── intent_user.md               # 意图解析 User Prompt 模板
│   ├── market_structure_*.md        # 市场结构分析 Prompt
│   ├── sector_route_*.md            # 因子路由决策 Prompt
│   ├── technical_*.md               # 技术面分析 Prompt
│   ├── fundamental_*.md             # 基本面分析 Prompt
│   ├── capital_*.md                 # 资金面分析 Prompt
│   ├── sentiment_*.md               # 情绪面分析 Prompt
│   └── fusion_*.md                  # 跨因子融合 Prompt
│
├── tools/                           # 工具模块（预留）
└── tests/                           # 测试
    ├── test_phase1.py               # Phase 1 集成测试
    └── test_phase2.py               # Phase 2 集成测试
```

---

## 关键依赖版本

```
Python 3.11.15
langgraph==1.1.10
openai==2.33.0
pydantic==2.13.3
python-dotenv==1.2.2
akshare==1.18.60
```

---

## 注意事项

1. **免责声明**：本系统输出仅供参考，不构成投资建议。股市有风险，投资需谨慎。

---

## License

MIT
