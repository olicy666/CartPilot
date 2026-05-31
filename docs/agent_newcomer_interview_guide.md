# CartPilot Agent 新手到面试指南

这份文档面向刚接触 Agent 应用的人，目标不是只让你“跑起来”，而是让你能完整解释 CartPilot 的设计取舍、代码路径、边界控制和面试价值。

读完并完成练习后，你应该能做到：

- 用 2 分钟讲清楚这个项目解决什么问题。
- 用 5-10 分钟讲清楚 Agent workflow、工具链、RAG、Human-in-the-loop、自检和评估。
- 能从用户输入一路追到最终推荐结果。
- 能回答面试官关于 LangGraph、受限自治、幻觉控制、RAG、评估、扩展性和生产化的追问。
- 能提出合理的下一步优化，而不是只会说“接入更大的模型”。

## 1. 项目一句话

CartPilot 是一个有边界的电商导购 Agent。它把自然语言购物需求解析成结构化购买任务卡，再通过商品检索、约束过滤、评论证据召回、排序、对比、推荐解释和自检生成可解释推荐。

项目核心不是“让大模型自由聊天”，而是把 LLM 放进一个受控 workflow：

- LLM 可以做高层决策：理解需求、生成追问、规划检索维度、组织推荐解释。
- 确定性代码负责硬边界：预算、排除项、商品事实、候选过滤、自检。
- 没有 API key 时仍可通过规则 fallback 跑完整流程。

面试时可以这样开场：

> 我做的是一个 bounded agentic shopping advisor。它不是简单 chatbot，也不是固定推荐系统，而是一个由 LangGraph 编排的导购 Agent：模型负责意图理解、追问、工具规划和解释，工具负责商品召回、约束过滤、评论 RAG、排序和自检。这样既能体现 Agent 的动态决策能力，又能避免模型绕过预算、排除项或编造商品事实。

## 2. 你需要先掌握的 Agent 基础

新手不要一上来背 LangGraph API。先掌握 Agent 应用的 8 个组成部分，再回到代码里找对应实现。

| Agent 概念 | 在 CartPilot 里的对应实现 | 你要会解释什么 |
| --- | --- | --- |
| 任务目标 | 购物导购和商品推荐 | 用户输入不是闲聊，而是一个购买决策任务 |
| State | `backend/agents/state.py` | workflow 节点之间传递的共享状态 |
| Planner | `backend/agents/agentic_planner.py` | LLM 决定追问、工具路径、评论检索维度、解释风格 |
| Tools | `backend/tools/*.py` | 搜索、过滤、召回、排序、对比、推荐、自检都是可控工具 |
| RAG | `backend/retrieval/review_vector_store.py` + `backend/tools/retrieve_reviews.py` | 从评论证据里找支持推荐和风险的依据 |
| Human-in-the-loop | `build_purchase_brief` + `await_user_confirmation` | 推荐前先让用户确认需求卡 |
| Guardrails | `filter_constraints.py` + `self_check.py` | 预算、排除项和事实校验不交给模型自由发挥 |
| Observability | `TraceStep` + Streamlit 调试面板 | 每一步为什么做、输入输出是什么都能看到 |

一句话总结：

> Agent = LLM 决策 + 工具执行 + 状态流转 + 约束边界 + 可观察性。CartPilot 把这五件事都落到了代码里。

## 3. 快速跑起来

先装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

运行 CLI demo：

```bash
python3 scripts/run_demo.py
```

运行一个自定义需求：

```bash
python3 scripts/run_demo.py "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"
```

运行 Streamlit UI：

```bash
streamlit run frontend/streamlit_app.py
```

运行 FastAPI：

```bash
uvicorn backend.api.app:app --reload
```

调用 API：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式",
    "require_confirmation": true,
    "use_llm": false
  }'
```

运行测试：

```bash
python3 -m unittest discover -s tests
```

运行小评估集：

```bash
python3 backend/evaluation/eval_agent.py
```

构建评论向量索引：

```bash
python3 scripts/build_review_index.py
```

## 4. 项目结构怎么读

推荐按这个顺序读，不要从 UI 开始，也不要先看所有 JSON。

```text
README.md
docs/project_design.md
backend/agents/workflow.py
backend/agents/graph.py
backend/agents/state.py
backend/models.py
backend/agents/intent_parser.py
backend/agents/purchase_brief.py
backend/agents/agentic_planner.py
backend/tools/*.py
backend/retrieval/*.py
backend/data/*.json
tests/*.py
frontend/streamlit_app.py
backend/api/app.py
```

每一层的职责：

| 目录 | 职责 |
| --- | --- |
| `backend/agents` | Agent workflow、状态、意图解析、任务卡、LLM planner |
| `backend/tools` | 可被 workflow 调用的确定性工具 |
| `backend/retrieval` | 品类识别和评论向量检索 |
| `backend/data` | 品类 profile、商品、评论、category skill pack |
| `backend/llm` | OpenAI-compatible Chat Completions 客户端 |
| `backend/evaluation` | 小规模评估集和指标计算 |
| `backend/api` | FastAPI 服务入口 |
| `frontend` | Streamlit 产品化 demo |
| `tests` | 单元测试，覆盖 workflow、planner、RAG、guardrails、evaluation |

注意：代码里 UI/API 标题有些地方仍使用 `CommerceMind-Agent`，仓库和 README 使用 `CartPilot`。面试时统一叫 CartPilot 即可，也可以说明这是早期命名遗留，不影响架构。

## 5. 从一次请求看完整链路

以这个 query 为例：

```text
预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累
```

入口在 `backend/agents/workflow.py`：

```python
agent = CommerceAgent()
response = agent.run(query=query)
```

`CommerceAgent.run()` 会组装初始 state，然后调用 `CommerceAgentGraph.invoke()`：

```text
query
user_id
require_confirmation
use_llm
brief_overrides
human_feedback
trace
workflow_status
```

核心 graph 在 `backend/agents/graph.py`：

```text
START
  -> intent_parser
  -> clarification 或 purchase_brief
  -> await_user_confirmation 或 product_search
  -> constraint_filter
  -> review_evidence
  -> rank_candidates
  -> comparison 或 recommendation
  -> self_check
  -> memory_update
  -> finalize
  -> END
```

你要能逐步说清楚每个节点：

| 节点 | 代码位置 | 输入 | 输出 | 面试解释 |
| --- | --- | --- | --- | --- |
| Intent Parser | `_intent_parser` | query、category profiles | `intent`、`profile`、`llm_meta` | 先用规则识别品类、预算、场景、硬约束；`use_llm=true` 时可让 LLM 改写 intent |
| Clarification | `_clarification` | 未识别品类的 state | 追问用户品类 | 不确定时停下来问，不强行推荐 |
| Purchase Brief | `_purchase_brief` | intent、用户记忆、人工反馈 | 购买任务卡、agent plan | 把需求整理成可确认的结构化任务 |
| Human-in-loop | `_await_user_confirmation` | purchase brief | 追问问题，不继续推荐 | 需要用户确认时在检索前暂停 |
| Product Search | `_product_search` | query、category、agent plan | candidates | 按品类和关键词召回商品 |
| Constraint Filter | `_constraint_filter` | candidates、intent | filtered、rejected | 用确定性代码执行预算和排除项 |
| Review Evidence | `_review_evidence` | filtered products、review plan | evidence_by_product | 围绕关注维度检索评论证据 |
| Rank Candidates | `_rank_candidates` | products、constraints、evidence | ranked_candidates | 综合预算、场景、参数、证据打分 |
| Comparison | `_comparison` | ranked products、dimensions | comparison_table | 对比型任务生成结构化表 |
| Recommendation | `_recommendation` | ranking、evidence | recommendations | 生成推荐理由、风险和证据 |
| Self Check | `_self_check` | recommendations、constraints | self_check | 检查是否超预算、命中排除项、缺证据 |
| Memory Update | `_memory_update` | intent、user_id | memory_update | 保存用户最近偏好 |
| Finalize | `_finalize` | recommendations、self_check | answer | 输出最终回答 |

## 6. State 是怎么流动的

`backend/agents/state.py` 定义了 `CommerceAgentState`。它是整个 workflow 的数据契约。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `query` | 用户原始购物需求 |
| `intent` | 结构化意图：品类、预算、场景、偏好、排除项 |
| `purchase_brief` | 可展示、可确认的购物任务卡 |
| `agent_plan` | Agent 对工具路径和 RAG 的规划 |
| `candidates` | 初步召回商品 |
| `filtered_products` | 硬约束过滤后的商品 |
| `rejected_products` | 被过滤掉的商品及原因 |
| `evidence_by_product` | 每个商品召回到的评论证据 |
| `ranked_candidates` | 打分排序后的候选 |
| `recommendations` | 最终推荐项 |
| `comparison_table` | 对比任务的结构化对比表 |
| `self_check` | 自检结果 |
| `trace` | 可观察调试轨迹 |
| `llm_meta` | LLM 是否启用、是否实际调用、失败原因、usage |

面试时不要只说“用 LangGraph 管状态”，要更具体：

> 我把 state 当作 workflow 节点之间的唯一数据契约。每个节点只读自己需要的字段，写回有限字段，并追加 TraceStep。这样调试时可以看到意图解析、过滤、检索、排序、自检每一步的输入输出。

## 7. 意图解析：规则优先，LLM 可增强

规则解析在 `backend/agents/intent_parser.py`。

它会抽取：

- `budget_max`：预算上限，比如 “2000以内”。
- `scenarios`：使用场景，比如通勤、办公、游戏、深度学习。
- `must_dimensions`：必须关注的决策维度，比如降噪、续航、舒适度、显卡。
- `exclude_specs`：明确排除项，比如不要入耳式、不要曲面屏。
- `soft_preferences`：软偏好，比如舒适、续航、性价比。
- `mentioned_products`：用户提到的具体商品。
- `task_type`：推荐还是对比。

品类识别在 `backend/retrieval/category_retriever.py`，根据品类别名、决策维度关键词、场景和风险词打分。

LLM 意图解析在 `backend/llm/intent_parser.py`。它的关键点：

- 给模型候选品类，不允许模型发明新 category id。
- 要求输出 JSON。
- 输出会经过 `_normalize_llm_intent` 清洗。
- 如果 LLM 不可用，则沿用规则结果。

面试重点：

> 这里不是让 LLM 直接输出最终推荐，而是让它把非结构化 query 转成可执行约束。即使 LLM 失败，规则 fallback 仍能跑完整 workflow。

## 8. Purchase Brief 和 Human-in-the-loop

`backend/agents/purchase_brief.py` 负责生成购买任务卡。

任务卡包含：

- 品类和命中的 alias。
- 预算上限。
- 使用场景。
- 必须关注的维度。
- 排除规格。
- 软偏好。
- 用户提到的商品。
- 决策维度和常见风险。
- 用户记忆。
- 需要追问的问题。

`require_confirmation=True` 时，workflow 会停在 `await_user_confirmation`：

```text
Purchase Brief -> Human-in-loop Checkpoint -> END
```

用户确认或补充后，再用 `human_feedback` 和 `brief_overrides` 继续跑完整推荐流程。

面试时可以这样解释：

> 购物推荐里用户需求经常不完整，比如没说预算、场景或不能接受的风险。我没有让系统直接猜，而是先生成 purchase brief，让用户确认后再检索和排序。这个 checkpoint 是 Human-in-the-loop 的产品化体现。

## 9. Agentic Planner 的 4 个能力

`backend/agents/agentic_planner.py` 是最像 Agent 的部分。它把 LLM 能力限制在四类高层决策里。

### 9.1 生成动态追问

函数：`build_agentic_questions`

输入：

- query
- current intent
- category profile
- user memory
- fallback questions

输出：

- 最多 4 个选择题。
- 选项贴合品类和当前需求。
- 不重复询问用户已说明的信息。

如果 LLM 不可用，则使用 `human_feedback.py` 里的规则问题。

### 9.2 归一化用户反馈

函数：`normalize_human_feedback_with_agent`

作用是把用户回答转换成结构化 overrides：

- `budget_max`
- `scenarios`
- `must_dimensions`
- `exclude_specs`
- `soft_preferences`
- `preference_weights`

注意：模型只负责结构化，不允许创造商品事实。

### 9.3 规划工具路径和 RAG 查询

函数：`plan_agent_workflow`

输出 `agent_plan`：

```json
{
  "tool_sequence": [
    "product_search",
    "constraint_filter",
    "review_vector_retrieval",
    "rank_candidates",
    "recommendation_explainer",
    "self_check"
  ],
  "search_top_k": 20,
  "need_comparison": false,
  "review_plan": {
    "aspects": ["comfort", "noise_cancellation"],
    "queries": ["通勤 降噪 戴久舒服"],
    "top_k": 3
  },
  "ranking_focus": ["budget", "scenario", "dimension", "evidence"],
  "recommendation_style": "简洁、可解释、引用评论证据"
}
```

即使 LLM 规划了路径，代码仍强制保留关键边界：

- `constraint_filter` 不能跳过。
- `self_check` 不能跳过。
- `search_top_k` 被限制在 5-30。
- `review_top_k` 被限制在 1-5。
- `aspects` 必须属于当前品类维度。

### 9.4 改写推荐解释

函数：`explain_recommendations_with_agent`

LLM 只基于已有输入改写：

- 商品价格。
- 商品参数。
- 商品 tags。
- 排序原因。
- 评论证据。

它不能凭空增加商品事实。输出也会再合并回原 recommendation。

面试时总结：

> 我把 LLM 放在 planner 和 explainer 的位置，而不是 executor 的位置。它可以决定问什么、看什么证据、怎么解释，但不能直接修改商品事实、绕过过滤或决定自检通过。

## 10. 工具层：Agent 能力的执行边界

`backend/tools` 里的文件是这个项目最重要的“边界层”。

| 工具 | 文件 | 作用 |
| --- | --- | --- |
| 商品搜索 | `search_products.py` | 按品类、品牌、tag、query token 召回候选 |
| 约束过滤 | `filter_constraints.py` | 过滤超预算、命中排除项、缺必要能力的商品 |
| 评论召回 | `retrieve_reviews.py` | 按商品和关注维度取评论证据 |
| 候选排序 | `rank_candidates.py` | 按预算、场景、参数、证据加权评分 |
| 商品对比 | `compare_products.py` | 生成对比表 |
| 推荐生成 | `generate_recommendation.py` | 生成推荐理由、风险和证据 |
| 自检 | `self_check.py` | 检查最终推荐有没有违反硬约束 |
| 记忆更新 | `update_user_memory.py` | 保存用户最近偏好 |

面试官可能问：“为什么这些不都交给 LLM？”

可以回答：

> 预算、排除项和商品事实属于硬约束，不适合交给概率模型。工具层用确定性代码保证这些约束一定被执行，LLM 只提供可解释性和动态规划能力。

## 11. Ranking 逻辑要会手算

`backend/tools/rank_candidates.py` 里每个商品的分数由四部分构成：

```text
score = budget + scenario + dimension + evidence
```

每一项都可以被 `preference_weights` 放大或缩小：

```text
budget    默认 1.0
scenario  默认 1.0
dimension 默认 1.0
evidence  默认 1.0
```

例如用户说“更看重真实口碑”，`human_feedback.py` 会把 `evidence` 权重提高。用户说“更看重参数/性能/续航”，则提高 `dimension` 权重。

各项含义：

- `budget_score`：预算内越便宜越高，超预算会负分，但通常超预算商品已在过滤阶段被剔除。
- `scenario_score`：商品 tags 命中用户场景越多越高。
- `dimension_score`：根据关注维度检查 specs 或 tags。
- `evidence_score`：评论证据里正向 aspect 加分，负向 aspect 扣分。

面试时可以说：

> 这个排序不是为了做复杂推荐算法，而是为了让候选排序可解释、可调试、可被测试。每个推荐项都有 `score_breakdown`，用户和开发者都能看到为什么排在前面。

## 12. RAG：评论证据召回

评论向量库在 `backend/retrieval/review_vector_store.py`。

它是一个轻量 SQLite vector store：

- 把 review content 和 aspects 拼成文档。
- 用 hashed text vector 转成固定维度向量。
- 存入 `.cache/review_vectors.sqlite`。
- 查询时计算 cosine similarity。
- 如果用户关注某些 aspect，会额外加 aspect bonus。

这不是生产级 embedding 检索，但它很适合面试项目：

- 依赖少，容易本地跑。
- 结构清楚，接口窄。
- 可以无缝替换成 Chroma、Qdrant、Milvus 或真实 embedding API。

RAG 链路：

```text
agent_plan.review_plan
  -> aspects
  -> queries
  -> retrieve_product_reviews
  -> ReviewVectorStore.search
  -> evidence_by_product
  -> rank_candidates
  -> generate_recommendation
  -> self_check
```

要讲清楚的重点：

> RAG 在这里不是把商品详情塞给模型，而是给推荐排序和解释提供评论证据。评论证据会影响打分，也会出现在推荐理由和风险提示里。

## 13. Guardrails：如何防止乱推荐

CartPilot 的 guardrails 分三层。

第一层：进入推荐前过滤。

`filter_constraints.py` 会剔除：

- 超预算商品。
- 用户明确排除的规格，比如 `form_factor=in_ear`。
- 不满足必须能力的商品，比如需要主动降噪但商品没有。

第二层：LLM 输出清洗。

`agentic_planner.py` 和 `llm/intent_parser.py` 会清洗模型输出：

- category 必须在候选品类内。
- decision dimension 必须属于当前品类。
- top_k 有上下限。
- tool name 必须在允许列表内。
- JSON 解析失败则 fallback。

第三层：最终自检。

`self_check.py` 检查：

- 推荐商品是否超预算。
- 是否命中排除项。
- 是否缺少评论证据。

面试回答模板：

> 我没有把安全性寄托在 prompt 上。Prompt 只是一层约束，真正的硬边界在工具和自检里。即使 LLM 规划错误，constraint filter 和 self-check 仍会拦住违反预算或排除项的推荐。

## 14. LLM 配置和 fallback 设计

LLM 客户端在 `backend/llm/client.py`，使用 OpenAI-compatible Chat Completions API。

配置方式：

```bash
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

也可以用本地 `llm.local.json`，但不要提交密钥。

关键设计：

- `LLMClient.is_configured` 判断是否有 API key。
- 没有 key 时返回 `llm_api_key_missing`。
- 调用失败、超时、JSON 解析失败都会返回 meta。
- workflow 继续使用规则 fallback。
- `llm_meta` 会记录启用状态和实际使用状态。

面试时说：

> 这个项目不是必须依赖外部模型才能演示。LLM 是增强能力，不是单点失败。没有 key 的情况下，规则解析、工具执行、RAG、排序和自检仍然可以完整跑通。

## 15. 数据层和品类扩展

核心数据文件：

| 文件 | 作用 |
| --- | --- |
| `backend/data/category_profiles.json` | 基础品类 profile |
| `backend/data/category_skills/*.json` | 可覆盖或扩展的品类 skill pack |
| `backend/data/products.json` | 商品数据 |
| `backend/data/reviews.json` | 评论数据和 aspect sentiment |

当前支持的品类包括：

- 耳机
- 笔记本电脑
- 平板
- 手机
- 显示器
- 投影仪
- 咖啡机
- 空气炸锅

新增品类的步骤：

1. 在 `category_profiles.json` 或 `category_skills/` 增加 category profile。
2. 补充 `decision_dimensions`、`required_specs`、`scenario_weights`、`common_risks`。
3. 在 `products.json` 增加该品类商品，保证 specs 覆盖 required specs。
4. 在 `reviews.json` 增加评论和 aspect sentiment。
5. 补充 eval case。
6. 补充或更新 tests。
7. 运行 `python3 -m unittest discover -s tests` 和 `python3 backend/evaluation/eval_agent.py`。

面试亮点：

> 新品类主要靠数据扩展，不需要改主 workflow。这体现了 category profile 和 skill pack 的分层设计。

## 16. UI、API 和 CLI 三个入口

### CLI

文件：`scripts/run_demo.py`

适合面试现场快速展示 JSON 输出：

```bash
python3 scripts/run_demo.py "预算2000以内，通勤降噪耳机，不要入耳式"
```

CLI 输出里重点看：

- `intent`
- `purchase_brief`
- `recommendations`
- `trace`
- `self_check`

### Streamlit

文件：`frontend/streamlit_app.py`

适合展示产品体验：

- 输入购物需求。
- 整理任务卡。
- 回答追问。
- 人工校准预算、排除商品、优先商品、排序权重。
- 查看推荐卡、评论证据、debug trace。

面试时可以打开 Streamlit，边点边解释 workflow。

### FastAPI

文件：`backend/api/app.py`

适合说明服务化能力：

- `GET /health`
- `POST /chat`

`ChatRequest` 支持：

- `query`
- `user_id`
- `require_confirmation`
- `use_llm`
- `brief_overrides`
- `human_feedback`

## 17. 测试和评估怎么讲

单元测试覆盖：

- workflow trace 和 self-check。
- 未知品类澄清。
- purchase brief 暂停确认。
- 人工反馈驱动推荐。
- preference weights 生效。
- 对比任务生成对比表。
- LLM 缺失时 fallback。
- Agent planner 的动态追问、反馈归一化、工具规划、解释改写。
- 品类识别。
- 评论向量检索。
- 小评估集运行。

评估集在 `backend/evaluation/test_cases.json`。

评估指标：

- `category_correct`
- `clarification_correct`
- `task_type_correct`
- `trace_contains_expected`
- `top_product_correct`

这不是大规模 benchmark，但足以证明项目不是只靠肉眼 demo。

面试时可以说：

> 这个项目的评估重点是 workflow 行为是否正确，而不是追求离线推荐指标。因为这是一个 Agent 应用，除了最终商品，还要验证是否识别对品类、是否该追问时追问、是否走过必要节点、是否命中预期 top product。

## 18. 推荐的 5 天学习路线

### 第 1 天：跑通和看输出

目标：知道项目做什么。

任务：

1. 跑 CLI 默认 demo。
2. 跑 Streamlit。
3. 跑测试。
4. 观察 `trace` 里每个节点。
5. 对照 README 画一遍流程图。

你需要能回答：

- 输入 query 后经过哪些节点？
- 最终推荐里有哪些字段？
- self-check 什么时候通过？

### 第 2 天：读 Agent workflow

目标：能从 `CommerceAgent.run()` 追到最终回答。

重点文件：

- `backend/agents/workflow.py`
- `backend/agents/graph.py`
- `backend/agents/state.py`
- `backend/models.py`

任务：

1. 标出 graph 里的所有 node 和 edge。
2. 找出两个 conditional route。
3. 跟踪一次普通推荐任务。
4. 跟踪一次未知品类任务。
5. 跟踪一次对比任务。

你需要能回答：

- 为什么 unknown category 会提前 END？
- comparison 是怎么触发的？
- trace 是在哪里追加的？

### 第 3 天：读工具和 guardrails

目标：能解释为什么模型不能乱推荐。

重点文件：

- `backend/tools/filter_constraints.py`
- `backend/tools/rank_candidates.py`
- `backend/tools/generate_recommendation.py`
- `backend/tools/self_check.py`
- `backend/agents/agentic_planner.py`

任务：

1. 手算一个商品为什么被过滤。
2. 手算一个商品的 `score_breakdown`。
3. 修改 query 让系统排除入耳式耳机。
4. 修改 query 触发对比任务。
5. 阅读 planner 输出清洗逻辑。

你需要能回答：

- 预算在哪里被执行？
- 排除项在哪里被执行？
- LLM 规划为什么不能跳过自检？
- 推荐理由来自哪里？

### 第 4 天：读 RAG、数据和评估

目标：能解释评论证据如何影响推荐。

重点文件：

- `backend/retrieval/review_vector_store.py`
- `backend/tools/retrieve_reviews.py`
- `backend/data/reviews.json`
- `backend/evaluation/eval_agent.py`
- `backend/evaluation/test_cases.json`

任务：

1. 构建 review index。
2. 找一个商品的 reviews。
3. 看 `matched_aspects` 如何进入 evidence。
4. 看 evidence 如何影响 ranking。
5. 跑 evaluation。

你需要能回答：

- 为什么这里用了 SQLite hashed vector？
- 以后怎么换成真实 embedding 和向量数据库？
- 评估集验证了哪些行为？

### 第 5 天：准备面试讲法和扩展方案

目标：能像项目作者一样答辩。

任务：

1. 准备 2 分钟 pitch。
2. 准备 10 分钟架构讲解。
3. 准备 5 个 demo query。
4. 准备 3 个项目不足。
5. 准备 3 个下一步优化。

你需要能回答：

- 为什么这是 Agent，而不是普通 RAG？
- 为什么需要 Human-in-the-loop？
- 如何防止 hallucination？
- 如何上线到生产？
- 如果数据规模扩大 100 倍怎么办？

## 19. 面试 Demo 脚本

### Demo 1：普通推荐

命令：

```bash
python3 scripts/run_demo.py "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"
```

讲解顺序：

1. Intent Parser 识别耳机、预算 2000、通勤/办公、不要入耳式。
2. Purchase Brief 整理任务卡。
3. Product Search 召回耳机。
4. Constraint Filter 剔除入耳式和超预算商品。
5. Review Evidence Retrieval 召回降噪和舒适度评论。
6. Rank Candidates 综合价格、场景、参数、证据排序。
7. Recommendation 输出理由和风险。
8. Self Check 确认推荐不违反硬约束。

### Demo 2：需要澄清

命令：

```bash
python3 scripts/run_demo.py "我想买个送朋友的东西，预算500"
```

讲解重点：

- 系统没有稳定识别品类。
- 进入 Clarification 节点。
- 不强行推荐，先问用户买哪类。

### Demo 3：对比任务

命令：

```bash
python3 scripts/run_demo.py "iPad Air、华为 MatePad Pro 和小米 Pad 这几个，哪个更适合记笔记和轻度剪视频？"
```

讲解重点：

- `task_type=comparison`。
- workflow 在 ranking 后进入 Comparison。
- 输出 `comparison_table`，再生成推荐。

### Demo 4：Human-in-the-loop

可以用 Streamlit：

```bash
streamlit run frontend/streamlit_app.py
```

操作：

1. 输入“我想买降噪耳机”。
2. 点击“整理任务卡”。
3. 观察右侧追问预算、场景、优先级、不能接受项。
4. 选择“预算2000以内”“通勤/办公”“真实口碑”“不要入耳式”。
5. 点击“回答并继续推荐”。

讲解重点：

- 需求不足时先问关键问题。
- 用户反馈被归一化成结构化 constraints。
- 人工校准可以影响排序权重和候选商品。

### Demo 5：LLM fallback

命令：

```bash
python3 scripts/run_demo.py "预算2000以内，买通勤降噪耳机"
```

讲解重点：

- 不配置 API key 也能跑。
- `use_llm=false` 时全部走规则和工具。
- `use_llm=true` 但无 key 时会记录 `llm_api_key_missing`，继续 fallback。

## 20. 面试高频问题和回答

### Q1：为什么这个项目算 Agent？

回答：

> 它不是一次性调用模型生成答案，而是一个有状态 workflow。系统会解析意图、必要时追问、规划工具调用、检索评论证据、排序候选、生成解释、自检并更新记忆。LLM 在其中承担 planner 和 explainer 角色，工具执行具体动作，state 串联所有节点。

### Q2：为什么用 LangGraph？

回答：

> 这个任务有明确多步骤流程和条件分支，比如未知品类要澄清、需要确认时暂停、对比任务要进入 comparison。LangGraph 适合表达 stateful workflow、node、edge 和 conditional routing。项目里也有一个 fallback adapter，让没有安装 LangGraph 的环境还能跑测试。

### Q3：LLM 具体做了什么？

回答：

> 开启 LLM 后，它做六类受限决策：意图解析、动态追问、反馈归一化、工具路径规划、评论检索规划、推荐解释改写。它不负责预算过滤、商品事实判断和最终自检。

### Q4：如何防止模型幻觉？

回答：

> 第一，模型输出必须是 JSON，并经过 schema 清洗。第二，商品事实来自 `products.json` 和 review evidence，不允许模型创造。第三，预算和排除项由 `filter_constraints.py` 执行。第四，推荐后用 `self_check.py` 检查是否违反硬约束或缺证据。

### Q5：为什么不用纯 RAG？

回答：

> 纯 RAG 更像问答，把资料召回后交给模型生成答案。但购物推荐需要结构化约束、候选过滤、排序、对比和自检。CartPilot 的 RAG 只是 evidence layer，真正的决策链由 workflow 和工具完成。

### Q6：为什么不用纯推荐系统？

回答：

> 传统推荐系统适合大规模用户行为数据和点击/购买预测，但用户这里输入的是自然语言、约束和场景。CartPilot 更像 decision assistant：先把需求结构化，再用工具和证据做可解释推荐。它可以和传统推荐系统结合，但不是同一个问题。

### Q7：Human-in-the-loop 的价值是什么？

回答：

> 购物需求经常不完整或含糊。与其让模型猜，不如先生成任务卡，让用户确认预算、场景、优先级和排除项。这样推荐前就能减少误解，也能把用户反馈结构化进后续工具链。

### Q8：RAG 是怎么做的？

回答：

> 评论数据会被转成 SQLite 里的 hashed vector。查询时，Agent plan 给出关注 aspects 和 query，系统对每个候选商品检索 top-k 评论证据。证据既进入 ranking 的 evidence score，也进入推荐理由和风险提示。

### Q9：SQLite hashed vector 有什么局限？

回答：

> 它不是语义 embedding，只是轻量 demo 方案，优点是依赖少、可本地运行、接口清楚。生产中我会替换成真实 embedding 模型和向量数据库，比如 Qdrant、Milvus、Chroma，并加 reranker。

### Q10：如何扩展新品类？

回答：

> 新增品类主要改数据：category profile、skill pack、products、reviews、eval cases 和 tests。主 workflow 不需要变化，因为它依赖统一的 CategoryProfile、Product、Review 和 tool interface。

### Q11：如何评估这个 Agent？

回答：

> 不能只看最终回答好不好，还要评估 workflow 行为。当前小评估集检查品类识别、是否该澄清、任务类型、是否经过预期节点、top product 是否符合预期。后续会扩展到更多 case，并加入人工标注的推荐质量和风险覆盖指标。

### Q12：如果面试官说规则太多，不够 Agentic，怎么回答？

回答：

> 这是有意设计。Agentic 不等于所有事情都交给 LLM。真实业务里硬约束要确定性执行，模型适合处理开放、模糊、上下文相关的决策，比如追问什么、检索什么证据、怎么解释。CartPilot 的重点是 bounded autonomy。

### Q13：如果数据量扩大怎么办？

回答：

> 商品搜索会从当前 lexical scoring 升级为搜索引擎或向量召回加 rerank；评论向量库替换成专门向量数据库；memory 从进程内 dict 换成 Redis 或 PostgreSQL；评估集扩大并进入 CI；trace 可以接入日志和可观测平台。

### Q14：生产化还缺什么？

回答：

> 缺真实商品数据接入、库存和价格实时性、用户权限和会话存储、在线评估、灰度发布、异常监控、prompt/version 管理、更强的安全策略，以及更完整的召回和 rerank。

### Q15：这个项目最大的技术亮点是什么？

回答：

> 亮点是把 Agent 能力拆成可控边界：LLM 负责动态理解和规划，工具负责执行，RAG 提供证据，自检保证约束，trace 提供可观察性。这个结构比单次 LLM 调用更接近可上线的 Agent 应用。

## 21. 面试时的 2 分钟 Pitch

可以直接背这个版本：

> CartPilot 是一个有边界的电商导购 Agent，用 LangGraph 编排购物决策 workflow。用户输入自然语言需求后，系统先识别品类、预算、场景、硬约束和软偏好，再生成 purchase brief。如果需求不完整，会通过 Human-in-the-loop 追问用户。确认后，工具链会召回商品、执行预算和排除项过滤、从评论向量库检索证据、按预算/场景/参数/证据排序，最后生成推荐理由、风险提示并做 self-check。
>
> 这个项目的核心设计是 bounded autonomy。LLM 可以做意图解析、动态追问、工具规划、RAG 查询规划和推荐解释，但不能绕过预算、修改商品事实或跳过自检。没有 LLM API key 时，系统也能通过规则 fallback 完整运行。它体现了 Agent workflow、RAG、Human-in-the-loop、工具调用、可解释推荐和 guardrails 的完整闭环。

## 22. 10 分钟架构讲解提纲

1. 背景：购物推荐不是简单问答，需要约束、证据、排序和解释。
2. 总体架构：入口层、Agent workflow、工具层、数据层、评估层。
3. State：`CommerceAgentState` 串联所有节点。
4. Workflow：Intent Parser -> Purchase Brief -> Search -> Filter -> RAG -> Rank -> Recommend -> Self Check。
5. LLM 边界：planner/explainer，不直接执行硬约束。
6. 工具层：每个工具职责单一，可测试。
7. RAG：评论证据影响排序和解释。
8. Human-in-the-loop：需求不完整时先确认。
9. Guardrails：过滤、自检、schema 清洗、fallback。
10. 评估和未来优化：eval cases、真实 embedding、向量 DB、checkpoint、线上观测。

## 23. 你应该亲手完成的练习

### 练习 1：追踪一次 workflow

任务：

1. 跑默认耳机 query。
2. 在输出 JSON 中找到 `trace`。
3. 把每个 step 的 `inputs` 和 `outputs` 复制到笔记里。
4. 写一句话解释每个 step 的作用。

验收标准：

- 你能不看文档说出完整链路。
- 你能指出 budget 和 exclude specs 在哪里生效。

### 练习 2：构造一个会被过滤的商品

任务：

1. 找一个入耳式耳机。
2. 用 query 写出“不要入耳式”。
3. 看 `rejected_products` 里是否出现该商品。

验收标准：

- 你能解释 `_violation_reasons` 为什么拒绝它。

### 练习 3：改变排序权重

任务：

1. 用 `brief_overrides` 设置 `preference_weights.evidence=2.0`。
2. 对比推荐结果和 `score_breakdown`。

验收标准：

- 你能解释评论证据为什么影响排名。

### 练习 4：新增一个 eval case

任务：

1. 在 `backend/evaluation/test_cases.json` 增加一个新 query。
2. 写预期品类和 trace steps。
3. 运行 `python3 backend/evaluation/eval_agent.py`。

验收标准：

- 评估脚本能跑。
- 你能解释新增 case 覆盖了什么行为。

### 练习 5：新增一个品类

任务：

1. 新增一个 category profile。
2. 增加 2-3 个商品。
3. 增加评论。
4. 增加测试或 eval case。

验收标准：

- CLI 能识别新品类。
- 推荐结果包含评论证据。
- tests 或 eval 通过。

## 24. 常见误区

### 误区 1：把 Agent 等同于大模型聊天

正确理解：

> Agent 应用的关键是任务分解、状态管理、工具执行和边界控制。LLM 是其中一个决策组件。

### 误区 2：只讲 LangGraph，不讲业务问题

正确理解：

> 面试官更关心你为什么这样设计。LangGraph 是实现手段，核心是购物决策需要条件分支、追问、工具链和自检。

### 误区 3：把所有能力都归功于 LLM

正确理解：

> 这个项目很多可靠性来自确定性代码。LLM 增强理解和解释，工具保证执行正确。

### 误区 4：只展示 UI，不解释 trace

正确理解：

> UI 只是产品入口。面试时一定要展示 trace，因为 trace 能证明 workflow 的每一步真实发生了。

### 误区 5：只说“可以接向量数据库”

正确理解：

> 要说清楚为什么当前 SQLite hashed vector 是 demo 方案，替换时接口在哪里，替换后 ranking 和 evidence 如何保持兼容。

## 25. 可改进方向

按优先级从高到低：

1. 接入真实 embedding 模型和向量数据库。
2. 增加 reranker，对商品召回和评论召回做二次排序。
3. 使用 LangGraph checkpoint/interrupt 实现可恢复 Human-in-the-loop。
4. 把 `InMemoryUserMemory` 换成 Redis 或数据库。
5. 扩大 eval cases 到 20-30 个高质量场景。
6. 引入 prompt/version 管理和 golden test。
7. 增加线上 trace、错误率、LLM fallback 率、self-check fail 率监控。
8. 引入真实商品价格、库存、售后和时效数据。
9. 增加多轮会话，让用户能继续追问“为什么不推荐 X”。
10. 增加更细的安全策略，比如品牌偏见、广告标记、利益冲突声明。

面试时不要把这些说成“缺陷很多”，而是说：

> 当前版本刻意保持轻量，方便展示 Agent 架构闭环。生产化时我会优先升级检索、持久化、评估和可观测性。

## 26. 最终掌握检查清单

如果下面问题你都能回答，基本可以拿这个项目去面试。

- [ ] 你能用一句话解释 CartPilot。
- [ ] 你能画出完整 workflow。
- [ ] 你能说清楚 `CommerceAgentState` 的关键字段。
- [ ] 你能解释 Intent Parser 的规则解析和 LLM 增强。
- [ ] 你能解释 Purchase Brief 的作用。
- [ ] 你能解释 Human-in-the-loop 为什么在检索前暂停。
- [ ] 你能解释 Agentic Planner 的四类能力。
- [ ] 你能解释为什么 LLM 不能执行硬约束。
- [ ] 你能解释商品搜索、过滤、RAG、排序、推荐、自检每个工具。
- [ ] 你能手算一个候选商品的排序分数大致来源。
- [ ] 你能解释评论 evidence 如何进入推荐理由和风险。
- [ ] 你能解释 self-check 检查什么。
- [ ] 你能解释没有 LLM API key 时如何 fallback。
- [ ] 你能运行 tests 和 evaluation。
- [ ] 你能新增一个品类或 eval case。
- [ ] 你能说出当前实现的局限和生产化升级方案。

## 27. 一句话收尾

CartPilot 的价值不在于“调用了大模型”，而在于它展示了一个可控 Agent 应用应该怎么拆：LLM 负责动态判断，工具负责可靠执行，RAG 负责证据，Human-in-the-loop 负责补齐需求，自检负责守住边界，trace 负责让整个过程可解释、可调试、可面试。
