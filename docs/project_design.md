# CommerceMind-Agent 设计说明

当前代码把项目拆成知识层、工具层和一条 LangGraph workflow。成熟 Agent 框架负责 harness，项目代码重点放在电商导购的 AI-native 工作流、品类 Skill、工具设计和有边界的 Agent 决策。

## 三类知识

- Category Profile：定义品类别名、决策维度、必要参数、场景权重和常见风险。
- Category Skill Pack：`backend/data/category_skills/*.json` 可以覆盖或扩展品类知识，新增品类不需要改主 workflow。
- Product Data：保存商品标题、品牌、价格、参数、描述和标签。
- Review Evidence：保存评论内容、评分和 aspect sentiment，并通过 Chroma 向量库支持证据召回；未安装 Chroma 时可回退 SQLite。

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

## Event-driven Shopping Copilot

为了把 Human-in-the-loop 从“推荐前确认”扩展到完整购物过程，项目新增了 `backend/agents/shopping_copilot.py`。它把用户购物行为建模为事件流，而不是只等待用户输入 query。

当前支持的事件包括：

- `search_submitted`：用户提交搜索词，系统生成 Purchase Brief。
- `assistant_question_answered`：用户回答追问，系统更新 intent 和任务卡。
- `product_viewed`：用户点进商品页，Copilot 检查当前商品是否违反硬约束，并召回评论证据。
- `review_section_opened`：用户打开评论区，Copilot 重点展示和当前需求相关的评论证据。
- `compare_added`：用户把商品加入对比，Copilot 自动生成对比表。
- `cart_added` / `cart_removed`：同步购物车状态，并在加购时做商品检查。
- `checkout_started`：下单前做 final checkout check。

Copilot 会维护 `ShoppingSessionState`：

```text
session_id
stage
query
intent
purchase_brief
current_product_id
viewed_products
compared_products
cart_products
signals
assistant_cards
```

这让系统从 query-driven workflow 升级为 event-driven side assistant：

```text
Shopping Event
  -> Session State Update
  -> Stage Detection
  -> Intervention Policy
  -> Product / Review Tooling
  -> Assistant Card
```

新增 API：

- `POST /shopping/events`
- `GET /shopping/sessions/{session_id}`

新增 demo：

```bash
streamlit run frontend/copilot_app.py
```

## 向量检索

默认向量检索由 `backend/retrieval/chroma_vector_store.py` 实现，商品和评论分别写入 `.cache/chroma` 下的持久化 Chroma collection。评论文本和 aspect 会被转换为 embedding，`Review Evidence Retrieval` 节点按用户 query 与关注维度进行 top-k 检索。`backend/retrieval/vector_store_factory.py` 负责选择向量库，默认优先 Chroma；如果环境没有安装 `chromadb`，会回退到原来的 SQLite store，保证本地测试和 demo 不被外部依赖阻塞。

后续可以继续增强：

- Product Search -> 向量检索 + rerank
- Human-in-loop -> LangGraph checkpoint / interrupt
- Memory -> Redis / SQLite / PostgreSQL

## LLM 接口

`backend/llm/client.py` 实现了 OpenAI-compatible Chat Completions 客户端，支持从环境变量或本地 `llm.local.json` 读取配置。`backend/llm/intent_parser.py` 负责把 query、候选品类和规则 fallback 一起发给模型，要求输出 JSON intent。`backend/agents/agentic_planner.py` 负责追问生成、反馈归一化、工具规划、RAG 查询规划和推荐解释，所有输出都会先做 schema 清洗，再交给确定性工具执行。

## 生产化骨架

当前版本保留虚拟商品和评论数据，但已经接入 9 类生产化能力的本地实现：

- Embedding / Vector DB：`backend/retrieval/embeddings.py` 提供本地 hash embedding 和 OpenAI-compatible embedding provider；`ChromaProductVectorStore` 与 `ChromaReviewVectorStore` 默认使用 Chroma 保存向量索引，SQLite 作为 fallback。设置 `EMBEDDING_PROVIDER=openai` 后可调用真实 embedding 接口。
- Reranker：`backend/tools/rerank.py` 对商品召回、评论证据和最终候选做二次排序，排序结果会写入 `score_breakdown.rerank` 和 evidence 的 `rerank_score`。
- 可恢复 Human-in-the-loop：`SQLiteCheckpointStore` 会按 `session_id` 保存等待确认的 purchase brief；同 session 带 `human_feedback` 继续请求时会自动恢复上一轮 query。
- 数据库记忆：默认用户偏好记忆从进程内 dict 改为 `.cache/user_memory.sqlite`。
- 扩展评估：`backend/evaluation/test_cases.json` 扩展到 20 条 case，并新增 `golden_cases.json` 与 golden workflow test。
- Prompt/version 管理：`backend/prompts/registry.py` 统一登记 prompt key 和 version，LLM meta 会携带 prompt 信息。
- 线上观测：`SQLiteRunMonitor` 记录 run trace，并统计总请求、LLM fallback 率、self-check fail 率、错误率；API 暴露 `/monitoring/metrics` 和 `/monitoring/traces`。
- 多轮会话：`SQLiteConversationStore` 保存同一 session 的历史回答，支持回答“为什么不推荐 X”这类基于上一轮推荐的追问。
- 安全策略：`backend/safety/policy.py` 检查广告/赞助披露、利益冲突披露和品牌集中风险，并写入 `self_check.safety_issues`。
