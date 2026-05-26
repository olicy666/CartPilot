# CommerceMind-Agent 设计说明

当前代码把项目拆成知识层、工具层和一条 LangGraph workflow。成熟 Agent 框架负责 harness，项目代码重点放在电商导购的 AI-native 工作流、品类 Skill、工具设计和有边界的 Agent 决策。

## 三类知识

- Category Profile：定义品类别名、决策维度、必要参数、场景权重和常见风险。
- Category Skill Pack：`backend/data/category_skills/*.json` 可以覆盖或扩展品类知识，新增品类不需要改主 workflow。
- Product Data：保存商品标题、品牌、价格、参数、描述和标签。
- Review Evidence：保存评论内容、评分和 aspect sentiment，并通过 SQLite 向量库支持证据召回。

## Workflow

```text
User Query
  -> Intent Parser
  -> Purchase Brief / Agentic Planner
  -> Human-in-loop Checkpoint optional
  -> Product Search
  -> Constraint Filter
  -> Review Evidence Retrieval with Agent-planned queries
  -> Rank Candidates
  -> Comparison optional
  -> Recommendation / Agent Explanation
  -> Self Check
  -> Memory Update
```

这个版本保留规则 fallback，同时在开启 `use_llm` 后把 6 类决策放权给 Agent：

- 动态决定需要追问什么。
- 动态生成选择题选项。
- 把 Human-in-loop 回答归一化成结构化约束和偏好。
- 为评论向量库规划 aspect 和 multi-query。
- 规划工具路径，例如是否需要对比、召回多少候选、证据优先级。
- 基于商品事实和评论证据生成推荐解释。

预算上限、用户明确排除项、商品事实过滤和 Self Check 仍由确定性代码执行。

## 评论向量库

`backend/retrieval/review_vector_store.py` 实现了一个轻量 SQLite 向量库。评论文本和 aspect 会被转换为归一化 hashed text vector，存入 `.cache/review_vectors.sqlite`。`Review Evidence Retrieval` 节点会按用户 query 与关注维度进行 top-k cosine 检索。这个接口后续可以替换为 Chroma、Qdrant 或 Milvus。

后续可以继续增强：

- Product Search -> 向量检索 + rerank
- Human-in-loop -> LangGraph checkpoint / interrupt
- Memory -> Redis / SQLite / PostgreSQL

## LLM 接口

`backend/llm/client.py` 实现了 OpenAI-compatible Chat Completions 客户端，支持从环境变量或本地 `llm.local.json` 读取配置。`backend/llm/intent_parser.py` 负责把 query、候选品类和规则 fallback 一起发给模型，要求输出 JSON intent。`backend/agents/agentic_planner.py` 负责追问生成、反馈归一化、工具规划、RAG 查询规划和推荐解释，所有输出都会先做 schema 清洗，再交给确定性工具执行。
