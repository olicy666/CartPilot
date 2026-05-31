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

## 生产化骨架

当前版本保留虚拟商品和评论数据，但已经接入 9 类生产化能力的本地实现：

- Embedding / Vector DB：`backend/retrieval/embeddings.py` 提供本地 hash embedding 和 OpenAI-compatible embedding provider；`ProductVectorStore` 与 `ReviewVectorStore` 使用 SQLite 保存向量索引。默认离线可跑，设置 `EMBEDDING_PROVIDER=openai` 后可调用真实 embedding 接口。
- Reranker：`backend/tools/rerank.py` 对商品召回、评论证据和最终候选做二次排序，排序结果会写入 `score_breakdown.rerank` 和 evidence 的 `rerank_score`。
- 可恢复 Human-in-the-loop：`SQLiteCheckpointStore` 会按 `session_id` 保存等待确认的 purchase brief；同 session 带 `human_feedback` 继续请求时会自动恢复上一轮 query。
- 数据库记忆：默认用户偏好记忆从进程内 dict 改为 `.cache/user_memory.sqlite`。
- 扩展评估：`backend/evaluation/test_cases.json` 扩展到 20 条 case，并新增 `golden_cases.json` 与 golden workflow test。
- Prompt/version 管理：`backend/prompts/registry.py` 统一登记 prompt key 和 version，LLM meta 会携带 prompt 信息。
- 线上观测：`SQLiteRunMonitor` 记录 run trace，并统计总请求、LLM fallback 率、self-check fail 率、错误率；API 暴露 `/monitoring/metrics` 和 `/monitoring/traces`。
- 多轮会话：`SQLiteConversationStore` 保存同一 session 的历史回答，支持回答“为什么不推荐 X”这类基于上一轮推荐的追问。
- 安全策略：`backend/safety/policy.py` 检查广告/赞助披露、利益冲突披露和品牌集中风险，并写入 `self_check.safety_issues`。
