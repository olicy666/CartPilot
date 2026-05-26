# CommerceMind-Agent 项目文档

## 面向电商导购决策的 Tool-Using LLM Agent 系统

> 本文档用于向其他大模型、开发者或面试官快速说明：我们想做的不是一个普通电商 RAG Chatbot，而是一个面向电商导购决策的多步骤 LLM Agent 系统。项目借鉴商品域 Agent 文章中的 Function-Centric Agent、Workflow 编排、商品知识库、AI 生产数据评测、事件驱动更新等思想，但实现上弱化 Java 企业工程属性，转向更适合 Agent / LLM 应用岗位展示的 Python Agent 应用系统。

---

## 1. 项目一句话概括

**CommerceMind-Agent** 是一个面向电商导购场景的 **Tool-Using LLM Agent 系统**。它不是普通的 RAG 问答机器人，而是一个能够围绕用户购物目标进行 **意图理解、任务规划、工具调用、商品检索、评论证据抽取、多商品比较、推荐决策、答案自检与用户偏好记忆** 的多步骤智能体系统。

项目核心目标是构建一个可以展示 Agent 能力的电商应用：用户输入自然语言购物需求后，系统不是直接生成回答，而是先解析用户约束和偏好，再动态调用商品搜索、属性过滤、评论检索、商品比较、推荐生成和自检工具，最终给出有证据支撑的商品推荐结果。

---

## 2. 项目背景

当前很多电商 AI 项目停留在“RAG + Chatbot”层面：把商品文档、商品详情页或评论向量化，然后让大模型基于召回内容回答问题。这种方案可以解决部分知识问答问题，但在真实导购场景中存在明显不足。

第一，用户需求往往不是一个简单问题，而是一个多约束决策任务。例如：

> “预算 3000 以内，通勤用，降噪好，续航强，不要入耳式耳机。”

这类任务需要结构化解析预算、场景、硬约束、软偏好和风险因素。

第二，普通 RAG 缺乏主动规划能力。它通常是“检索一次，然后回答”，但导购任务经常需要多步处理：先澄清需求，再检索候选商品，再过滤参数，再查评论，再比较优缺点，最后生成推荐解释。

第三，普通 RAG 缺乏工具调用能力。商品推荐不是纯文本生成问题，还需要调用商品检索、价格过滤、规格解析、评论聚合、相似商品比较、偏好记忆等外部工具。

第四，普通 RAG 缺乏可评测性。导购 Agent 的质量不能只看回答是否流畅，还要评估工具调用是否正确、推荐是否满足约束、证据是否支持结论、是否出现幻觉、是否多问或漏问澄清问题。

因此，本项目将电商导购系统从“RAG 问答”升级为 **Agentic Product Decision System**，即一个以任务完成为核心、以工具调用为执行方式、以商品知识库为基础、以评测体系为保障的电商 Agent 系统。

---

## 3. 项目借鉴的核心思想

项目借鉴了商品域 Agent 架构中的几个关键思想，但不复刻其 Java 工程体系。

原始商品 Agent 文章提出了“事件驱动的 Function-Centric Agent 架构”，采用两层设计：

- 上层是业务场景 workflow 编排层；
- 下层是统一能力供给层；
- 两层之间通过 AIFunction 标准化封装工具和领域知识；
- 系统整合显性事实、关联情景、隐性经验三类商品知识库；
- 支持商品属性、卖点、摘要、SKU 参数等场景；
- 强调在线/离线流程统一、AI 生产数据评测和商品事件驱动实时推理。

本项目保留其思想，但进行应用化改造：

| 原商品 Agent 思想 | 本项目改造方式 |
|---|---|
| AIFunction | Python function schema / tool schema |
| AIWorkflow | LangGraph 状态图 / Agent workflow |
| 商品知识库 | 商品参数库、评论证据库、图文多模态知识库、用户偏好记忆 |
| 商品事务事件 | 商品价格变化、评论新增、商品图片更新、商品属性变更等事件驱动更新机制 |
| AI 生产数据质量评测 | Agent 行为轨迹评测、工具调用准确率、约束满足率、证据一致性和幻觉率 |

项目最终定位不是“淘天商品后台系统”，而是一个更适合 Agent / LLM 应用岗位展示的 **电商导购决策 Agent**。

---

## 4. 项目名称

推荐名称：

**CommerceMind-Agent: A Tool-Using LLM Agent for Evidence-Grounded Product Recommendation**

中文名称：

**CommerceMind-Agent：面向证据支撑商品推荐的工具调用型电商导购 Agent**

备选名称：

- **ShopAgent-X：面向多轮导购决策的 LLM Agent 系统**
- **ProductMind-Agent：商品知识驱动的多步骤导购智能体**
- **EcomAgent：基于工具调用与商品知识库的电商决策 Agent**

---

## 5. 项目核心目标

本项目要实现的不是一个普通客服机器人，而是一个能完成复杂购物决策流程的 Agent 系统。

具体目标包括：

1. 将用户自然语言购物需求解析为结构化约束，包括预算、品类、使用场景、硬性要求、软偏好、排除项和风险偏好。
2. 构建商品知识库，将商品标题、参数、详情页、评论、图片 caption、OCR 信息、品牌信息和场景标签统一组织。
3. 构建工具调用层，将商品检索、属性过滤、评论检索、商品比较、推荐排序、卖点生成、答案自检等能力封装为可被 LLM 调用的 tools。
4. 使用 Agent workflow 实现多步骤任务规划，使系统根据当前状态决定下一步是澄清问题、检索商品、过滤候选、调用评论工具、比较商品，还是生成最终回答。
5. 实现用户偏好记忆，使 Agent 能在多轮对话中保留用户预算、品牌偏好、场景偏好、风险偏好等长期信息。
6. 实现 evidence-grounded recommendation，即每个推荐结论都必须能回溯到商品参数、评论证据或用户偏好，而不是无依据生成。
7. 构建 Agent 评测体系，从工具调用、约束满足、证据一致性、推荐相关性和幻觉率等角度评估系统质量。

---

## 6. 项目边界

本项目不做完整电商平台，不做支付、订单、库存、物流、商家后台，也不强调 Java 企业级架构。

本项目的重点是 Agent / LLM 应用能力：

- 任务规划；
- 工具调用；
- RAG 检索；
- 多轮对话；
- 用户记忆；
- 商品知识组织；
- 推荐解释；
- 行为轨迹评测；
- 多模态商品理解。

这使得项目更适合投递以下岗位：

- LLM 应用开发；
- Agent 应用工程师；
- AI 产品算法工程师；
- RAG / Agent 工程师；
- 多模态应用工程师；
- 智能客服 / 智能导购方向算法工程师。

---

## 7. 核心用户场景

### 7.1 场景一：约束型商品导购

用户输入：

> “我想买一个 3000 元以内的降噪耳机，主要通勤用，续航要好，不想要佩戴压迫感太强的。”

Agent 执行流程：

1. 解析用户需求：品类=耳机，预算≤3000，场景=通勤，核心偏好=降噪、续航、舒适度。
2. 判断是否需要澄清：是否接受头戴式、是否需要苹果生态、是否关注麦克风。
3. 调用商品搜索工具，召回候选耳机。
4. 调用参数过滤工具，剔除预算不符或续航不足商品。
5. 调用评论检索工具，抽取关于“降噪、续航、佩戴舒适度”的用户评论证据。
6. 调用商品比较工具，比较候选商品优缺点。
7. 调用推荐生成工具，输出 Top-3 推荐。
8. 调用 self-check 工具，检查是否满足预算、场景和证据一致性。

输出结果不是一句简单推荐，而是：

- 推荐商品；
- 满足哪些硬约束；
- 适合哪些使用场景；
- 来自评论或参数的证据；
- 潜在风险；
- 不推荐哪些商品及原因。

### 7.2 场景二：多商品对比

用户输入：

> “iPad Air、华为 MatePad Pro 和小米 Pad 这几个，哪个更适合记笔记和轻度剪视频？”

Agent 执行流程：

1. 识别任务类型：多商品比较。
2. 提取比较维度：手写体验、屏幕、性能、生态、视频剪辑能力、价格。
3. 检索每个商品的参数和评论。
4. 根据用户场景构建权重：记笔记权重高，轻度剪视频次之。
5. 输出对比表。
6. 给出推荐结论和适用人群。
7. 给出“不适合选择某款”的边界条件。

### 7.3 场景三：商品属性补全与卖点生成

输入商品标题、详情页文本和商品图片。

Agent 执行流程：

1. 从标题和详情页中抽取品牌、型号、材质、尺寸、功能、适用场景。
2. 从图片 caption / OCR 中抽取视觉属性，例如颜色、形态、包装、关键文字。
3. 检查商品属性是否缺失。
4. 调用评论摘要工具提取用户高频关注点。
5. 生成商品卖点。
6. 调用事实一致性检查工具，避免卖点中出现无证据夸大。
7. 输出结构化商品画像。

这个场景对应原始商品 Agent 文章中的“商品属性、卖点、摘要”等核心落地场景，但本项目把它改造为可展示的 Agent workflow。

---

## 8. 系统总体架构

系统由六层组成：

```text
用户交互层
  ↓
Agent 编排层
  ↓
工具调用层
  ↓
商品知识层
  ↓
记忆与状态层
  ↓
评测与可观测层
```

### 8.1 用户交互层

负责接收用户自然语言输入，并输出流式回答、商品卡片、对比表和推荐解释。

可选技术：

- React / Next.js；
- Streamlit；
- Gradio；
- Flutter / React Native；
- WebSocket streaming。

MVP 阶段建议使用 Streamlit 或 React + FastAPI。

### 8.2 Agent 编排层

负责控制 Agent 的推理流程。

建议使用 **LangGraph** 实现状态机式 Agent，而不是简单 LangChain chain。原因是 LangGraph 更适合表达多节点、多条件路由、多轮状态更新和工具调用轨迹。

核心节点包括：

- **Intent Parser Node**：解析用户意图和约束。
- **Clarification Node**：判断是否需要追问。
- **Product Search Node**：召回候选商品。
- **Constraint Filter Node**：过滤不满足硬约束的商品。
- **Evidence Retrieval Node**：检索评论、参数、图片证据。
- **Comparison Node**：多商品比较。
- **Recommendation Node**：生成推荐结果。
- **Self-Check Node**：检查约束满足和证据一致性。
- **Memory Update Node**：更新用户偏好记忆。

### 8.3 工具调用层

工具调用层是本项目的核心，类似原文中 AIFunction 的 Python 化实现。

每个工具都需要有明确的输入 schema、输出 schema、描述、适用条件和失败处理方式。

建议实现以下 tools：

```python
search_products(query, category, budget_range, top_k)
```

根据用户需求召回候选商品。

```python
filter_by_constraints(products, constraints)
```

根据预算、品牌、参数、使用场景过滤商品。

```python
retrieve_product_reviews(product_id, aspects)
```

检索某个商品在指定方面的评论证据，例如续航、噪音、舒适度、质量。

```python
extract_product_specs(product_text, product_image_caption)
```

从商品文本和图片描述中抽取结构化参数。

```python
compare_products(product_ids, user_goal, dimensions)
```

按用户目标比较多个商品。

```python
rank_candidates(products, user_preferences, evidence)
```

根据约束满足度、评论证据和用户偏好进行排序。

```python
generate_recommendation(ranked_products, evidence, user_constraints)
```

生成最终推荐解释。

```python
self_check_answer(answer, constraints, evidence)
```

检查回答是否满足约束、是否有证据支持、是否存在幻觉。

```python
update_user_memory(user_id, preferences)
```

更新用户偏好记忆。

### 8.4 商品知识层

商品知识层包括四类数据。

#### 8.4.1 显性事实知识

包括商品品牌、型号、价格、尺寸、颜色、材质、续航、容量、芯片、屏幕、重量等客观参数。对应原文中的“显性事实知识”，即对商品属性和类目事实的客观描述。

#### 8.4.2 关联情景知识

包括商品与使用场景的关系，例如“通勤”“学生党”“小户型”“露营”“游戏”“办公”“健身”“送礼”。这类知识用于把商品参数转换成用户可理解的场景价值。

#### 8.4.3 隐性经验知识

包括用户评论、专家测评、品牌口碑、常见 bad case、优缺点总结。例如“佩戴两小时后耳朵压迫感明显”“风噪场景下通话效果一般”。这类知识可以增强推荐解释的可信度。

#### 8.4.4 多模态商品知识

包括商品图片 caption、OCR 信息、视觉属性、包装信息、颜色、款式、材质感、商品主体识别结果等。它用于支持商品图文联合理解。

---

## 9. 数据来源

MVP 可以使用公开数据集或自建小规模数据。

推荐数据来源：

- Amazon Reviews 2023；
- Amazon product metadata；
- Kaggle 电商商品数据集；
- 公开商品评论数据；
- 合法公开商品页面的少量样本；
- 手工构造 100–500 条高质量商品样本。

建议首期选择一个垂直品类，不要一开始做全品类。可选品类：

- 耳机；
- 笔记本电脑；
- 平板电脑；
- 咖啡机；
- 运动鞋；
- 家用投影仪；
- 空气炸锅。

推荐从“耳机”或“笔记本电脑”开始，因为参数结构清晰、评论维度丰富、用户导购需求明显。

---

## 10. 数据结构设计

### 10.1 商品表 Product

```json
{
  "product_id": "P001",
  "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
  "category": "headphones",
  "brand": "Sony",
  "price": 2499,
  "specs": {
    "type": "over-ear",
    "noise_cancellation": true,
    "battery_life": "30h",
    "weight": "250g",
    "bluetooth_version": "5.2"
  },
  "description": "商品详情文本",
  "image_urls": [],
  "image_captions": [],
  "tags": ["通勤", "降噪", "头戴式", "长续航"]
}
```

### 10.2 评论表 Review

```json
{
  "review_id": "R001",
  "product_id": "P001",
  "rating": 4,
  "content": "降噪效果很好，但是夏天戴久了有点闷。",
  "aspects": {
    "noise_cancellation": "positive",
    "comfort": "negative",
    "battery": "positive"
  }
}
```

### 10.3 用户偏好 Memory

```json
{
  "user_id": "U001",
  "budget_range": [1000, 3000],
  "preferred_brands": ["Sony", "Bose"],
  "rejected_brands": [],
  "usage_scenarios": ["通勤", "办公"],
  "risk_preferences": {
    "avoid_heavy_products": true,
    "care_about_after_sales": true
  },
  "conversation_summary": "用户偏好通勤降噪耳机，关注舒适度和续航。"
}
```

### 10.4 Agent State

```json
{
  "user_query": "预算3000以内，通勤用，想买降噪耳机",
  "intent": "product_recommendation",
  "constraints": {
    "category": "headphones",
    "budget_max": 3000,
    "must_have": ["noise_cancellation", "long_battery"],
    "scenario": ["commuting"]
  },
  "candidate_products": [],
  "retrieved_evidence": [],
  "tool_history": [],
  "need_clarification": false,
  "final_answer": null
}
```

---

## 11. Agent Workflow 设计

核心 workflow 如下：

```text
User Query
  ↓
Intent Parser
  ↓
Need Clarification?
  ├── Yes → Clarification Question → User Response → Intent Parser
  └── No
        ↓
Product Search Tool
        ↓
Constraint Filter Tool
        ↓
Evidence Retrieval Tool
        ↓
Candidate Ranking Tool
        ↓
Comparison / Recommendation Tool
        ↓
Self-Check Tool
        ↓
Final Answer + Product Cards + Evidence
        ↓
Memory Update
```

关键点是：Agent 的每一步都应该显式记录在 trace 中，包括：

- 调用了哪个工具；
- 工具输入是什么；
- 工具输出是什么；
- 为什么选择这个工具；
- 该工具结果如何影响后续决策；
- 最终答案引用了哪些证据。

这使项目在面试时可以展示“Agent 行为轨迹”，而不是只展示最终聊天结果。

---

## 12. 前端展示形式

前端不需要复杂，但必须能体现 Agent 特性。

建议页面包括：

- 左侧：用户对话窗口；
- 中间：推荐商品卡片；
- 右侧：Agent trace 面板；
- 底部：证据来源与评测结果。

商品卡片应展示：

- 商品名；
- 价格；
- 核心参数；
- 推荐理由；
- 风险提示；
- 评论证据；
- 匹配用户需求的维度；
- 不匹配的维度。

Agent trace 面板展示：

```text
Step 1: Intent Parser
Step 2: Product Search Tool
Step 3: Constraint Filter Tool
Step 4: Review Retrieval Tool
Step 5: Ranking Tool
Step 6: Self-Check Tool
```

这会让项目看起来明显区别于普通聊天机器人。

---

## 13. 评测体系

评测是本项目的关键加分项。不要只做 demo，需要准备一个小型 benchmark。

### 13.1 工具调用准确率

评估 Agent 是否调用了正确工具。

例子：

用户要求“比较 A 和 B”，正确行为应该调用 `compare_products`，而不是只调用 `search_products`。

指标：

- Tool Call Accuracy；
- Tool Sequence Accuracy；
- Tool Argument Accuracy。

### 13.2 约束满足率

评估推荐商品是否满足用户硬约束。

例如：

- 预算≤3000；
- 必须支持降噪；
- 必须适合通勤；
- 不能推荐入耳式。

指标：

- Constraint Satisfaction Rate。

### 13.3 证据一致性

评估推荐理由是否被商品参数或评论证据支持。

例如系统说“续航强”，证据中应有电池时长或评论支持。

指标：

- Evidence Support Rate；
- Faithfulness Score。

### 13.4 推荐相关性

评估推荐商品和用户需求的匹配程度。

指标：

- Recall@K；
- NDCG@K；
- MRR；
- 人工偏好评分。

### 13.5 幻觉率

评估回答中是否出现商品库中不存在的参数、价格、功能或评论。

指标：

- Hallucination Rate。

### 13.6 澄清问题质量

评估 Agent 是否在必要时追问，以及是否避免无意义追问。

指标：

- Clarification Precision；
- Clarification Recall；
- Unnecessary Question Rate。

---

## 14. MVP 实现范围

为了保证项目可落地，MVP 不做全量电商系统，只做一个垂直品类。

推荐 MVP 范围：

- 品类：耳机或笔记本电脑；
- 商品数量：100–500 个；
- 评论数量：每个商品 20–100 条；
- 工具数量：6–8 个；
- Agent workflow：1 个主 workflow + 2 个子 workflow；
- 评测样本：50–100 条用户请求；
- 前端：一个可交互 Demo 页面。

MVP 必须完成：

1. 商品数据清洗和入库；
2. 商品文本、评论、图片 caption 向量化；
3. 商品搜索工具；
4. 参数过滤工具；
5. 评论证据检索工具；
6. 多商品比较工具；
7. 推荐生成工具；
8. 答案自检工具；
9. LangGraph Agent workflow；
10. 简单用户偏好 memory；
11. Agent trace 可视化；
12. 小规模评测集。

---

## 15. 技术栈建议

### 15.1 后端

- Python；
- FastAPI；
- Pydantic；
- LangGraph；
- LangChain / LlamaIndex；
- OpenAI-compatible LLM API / Qwen / DeepSeek；
- PostgreSQL / SQLite；
- Chroma / Qdrant / Milvus；
- Redis，可选。

### 15.2 多模态

- CLIP；
- BLIP / Qwen-VL / GPT-4o-mini Vision；
- PaddleOCR / EasyOCR。

### 15.3 评测

- Ragas；
- DeepEval；
- LangSmith，可选；
- 自定义评测脚本。

### 15.4 前端

- Streamlit，适合快速 demo；
- React + FastAPI，适合简历展示。

### 15.5 部署

- Docker Compose；
- 本地可运行；
- README 提供启动命令和 demo case。

---

## 16. 项目目录结构建议

```text
CommerceMind-Agent/
  README.md
  docs/
    project_design.md
    agent_workflow.md
    evaluation.md
  backend/
    app.py
    api/
    agents/
      graph.py
      nodes.py
      state.py
    tools/
      search_products.py
      filter_constraints.py
      retrieve_reviews.py
      compare_products.py
      rank_candidates.py
      self_check.py
    memory/
      user_memory.py
    retrieval/
      index_builder.py
      retriever.py
      reranker.py
    data/
      products.json
      reviews.json
    evaluation/
      test_cases.json
      eval_agent.py
      metrics.py
  frontend/
    streamlit_app.py
  scripts/
    build_index.py
    run_demo.py
  docker-compose.yml
  requirements.txt
```

---

## 17. 项目创新点

本项目的创新点不在于模型训练，而在于 Agent 应用架构设计。

### 17.1 状态机式 Agent workflow

系统不是单轮 RAG，而是状态机式 Agent workflow。Agent 会根据任务状态决定是否澄清、检索、过滤、比较、生成或自检。

### 17.2 标准化工具调用层

系统将商品能力封装为标准化工具。商品检索、评论检索、属性抽取、商品比较、推荐排序和答案自检都不是 prompt 里的隐式能力，而是显式 tools。

### 17.3 Evidence-grounded recommendation

每个推荐理由都必须绑定商品参数、评论证据或用户偏好，降低幻觉。

### 17.4 用户偏好 memory

Agent 可以在多轮对话中持续维护预算、品牌偏好、场景偏好和风险偏好。

### 17.5 Agent 行为评测

不仅评估最终回答，还评估工具调用轨迹、参数正确性、约束满足率和证据一致性。

### 17.6 事件驱动的商品知识更新

系统支持事件驱动的商品知识更新。当商品价格、评论、图片或属性变化时，只触发局部更新流程，而不是全量重建知识库。这个思想来自原文中通过商品事务事件支撑实时 Agent 推理的设计，但本项目将其简化为适合 demo 的事件队列机制。

---

## 18. 与普通 RAG 电商 Chatbot 的区别

普通 RAG 电商 Chatbot：

```text
用户提问
  ↓
检索文档
  ↓
LLM 生成回答
```

CommerceMind-Agent：

```text
用户提问
  ↓
解析目标和约束
  ↓
判断是否需要澄清
  ↓
动态选择工具
  ↓
检索商品
  ↓
过滤硬约束
  ↓
抽取评论证据
  ↓
比较候选商品
  ↓
根据用户偏好排序
  ↓
生成推荐解释
  ↓
执行答案自检
  ↓
更新用户记忆
  ↓
输出商品卡片和证据链
```

核心区别是：**RAG 是一个工具，Agent 是任务控制器。** 本项目中 RAG 只负责知识召回，Agent 负责任务分解、工具选择、状态维护和决策生成。

---

## 19. 面试讲解口径

### 19.1 项目一句话解释

我做的不是普通电商 RAG 问答，而是一个面向商品导购决策的 Tool-Using LLM Agent。系统会先把用户自然语言需求解析为结构化约束，然后通过 LangGraph 控制多步骤 workflow，动态调用商品检索、参数过滤、评论证据检索、多商品比较、推荐排序和答案自检等工具。RAG 在系统中只是证据检索工具之一，真正的核心是 Agent 的任务规划、工具调用、状态管理和行为评测。

### 19.2 如果面试官问：为什么不用普通 RAG？

因为导购任务本质上是多约束决策，不是单轮知识问答。普通 RAG 很难处理需求澄清、硬约束过滤、多商品比较、用户偏好记忆和工具调用轨迹评测。我的系统把这些步骤显式建模成 Agent workflow，因此更适合复杂导购任务。

### 19.3 如果面试官问：项目难点是什么？

主要难点有三个。

第一，如何把用户模糊需求解析成可执行约束。

第二，如何让 Agent 正确选择工具，而不是把所有能力都塞进 prompt。

第三，如何评估 Agent 的行为质量，所以我设计了工具调用准确率、约束满足率、证据一致性、推荐相关性和幻觉率等指标。

---

## 20. 简历描述版本

### 20.1 项目名称

**CommerceMind-Agent：面向电商导购决策的 Tool-Using LLM Agent 系统**

### 20.2 简历项目描述

基于 LangGraph、LLM Function Calling、向量检索和 Agent Evaluation 构建面向电商导购场景的多步骤智能体系统。系统将用户自然语言购物需求解析为结构化约束，动态调用商品检索、参数过滤、评论证据检索、多商品比较、推荐排序和答案自检等工具，实现从用户需求理解到证据支撑商品推荐的端到端决策流程。构建商品参数、评论证据、图片 caption 和用户偏好记忆组成的商品知识库，支持多轮澄清、个性化推荐和可追溯解释。设计自动化评测集，从工具调用准确率、约束满足率、证据一致性、推荐相关性和幻觉率等维度评估 Agent 行为质量。

### 20.3 简历 bullet 版本

- 使用 LangGraph 构建状态机式 Agent workflow，实现意图解析、条件路由、工具调用、多轮澄清、推荐生成和答案自检。
- 设计商品检索、参数过滤、评论证据检索、多商品比较、推荐排序、用户记忆更新等 tools，并通过 Pydantic schema 约束输入输出。
- 构建商品多源知识库，将商品参数、详情文本、用户评论和图片 caption 统一索引，实现 evidence-grounded recommendation。
- 引入用户偏好 memory，结构化维护预算、品牌偏好、使用场景、风险偏好等信息，用于多轮个性化推荐。
- 搭建 Agent 评测集，统计工具调用准确率、约束满足率、证据一致性、推荐相关性和幻觉率，并通过 trace 分析失败路径。

---

## 21. 开发里程碑

### 21.1 第一阶段：数据与知识库

目标：完成商品数据清洗、评论解析、图片 caption 和向量索引。

任务：

1. 选择一个垂直品类。
2. 准备商品 metadata。
3. 准备用户评论。
4. 生成或导入商品图片 caption。
5. 构建商品结构化表。
6. 构建评论向量库。
7. 构建商品描述向量库。

### 21.2 第二阶段：工具层

目标：完成可被 Agent 调用的核心 tools。

任务：

1. `search_products`
2. `filter_by_constraints`
3. `retrieve_product_reviews`
4. `compare_products`
5. `rank_candidates`
6. `generate_recommendation`
7. `self_check_answer`
8. `update_user_memory`

### 21.3 第三阶段：Agent Workflow

目标：使用 LangGraph 串联完整导购流程。

任务：

1. 定义 Agent state。
2. 实现 intent parser node。
3. 实现 clarification node。
4. 实现 tool routing。
5. 实现 recommendation workflow。
6. 实现 memory update。
7. 记录 tool trace。

### 21.4 第四阶段：前端 Demo

目标：做一个可以展示的交互界面。

任务：

1. 用户输入框。
2. 流式回答。
3. 商品卡片。
4. 推荐证据展示。
5. Agent trace 展示。
6. 对比表展示。

### 21.5 第五阶段：评测

目标：构建项目可信度。

任务：

1. 构造 50–100 条用户请求。
2. 标注期望工具序列。
3. 标注硬约束。
4. 标注推荐相关性。
5. 计算工具调用准确率。
6. 计算约束满足率。
7. 计算证据一致性。
8. 分析 bad case。

---

## 22. 最小 Demo 示例

用户输入：

> “预算 2000 以内，想买一个适合通勤和办公室用的降噪耳机，戴久一点不要太累。”

系统输出：

```text
我会优先考虑以下约束：
1. 价格不超过 2000 元；
2. 具备主动降噪；
3. 适合通勤和办公室；
4. 评论中舒适度评价不能明显偏差；
5. 续航需要满足日常通勤使用。

推荐排序：

Top 1: 商品 A
推荐理由：满足预算，主动降噪评价较高，评论中多次提到长时间佩戴较舒适。
证据：
- 参数：主动降噪，续航 35 小时，重量 240g。
- 评论：多数用户提到“办公室佩戴不夹头”“地铁降噪明显”。
风险：夏季佩戴可能偏闷。

Top 2: 商品 B
推荐理由：续航更强，价格更低，但舒适度评论略弱。
风险：部分用户反馈头梁压迫感较明显。

不推荐商品 C：
虽然降噪强，但价格超过预算，且评论中多次出现佩戴压迫感。
```

右侧 trace：

```text
Intent Parser → Product Search → Constraint Filter → Review Retrieval → Ranking → Self Check → Final Answer
```

---

## 23. 项目最重要的判断

这个项目的成败不在于页面多漂亮，也不在于接了多少模型，而在于是否能清楚证明：

1. 它不是普通 RAG。
2. 它有显式 Agent workflow。
3. 它有真实 tools。
4. 它有用户状态和偏好 memory。
5. 它有证据支撑推荐。
6. 它有行为轨迹和评测。
7. 它能处理多轮、不完整、有约束的真实导购任务。

如果只实现“商品向量检索 + LLM 回答”，这个项目简历价值一般。

如果实现“Tool-Using Agent + 商品知识库 + 用户偏好记忆 + 证据推荐 + Agent 评测”，它就可以作为一个较完整的 LLM Agent 应用项目。
