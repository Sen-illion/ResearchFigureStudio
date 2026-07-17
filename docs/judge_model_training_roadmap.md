# ResearchFigureStudio Judge Model 训练与协同优化总路线

> 文档状态：主执行文档  
> 当前版本：v1.0  
> 更新日期：2026-07-15  
> 适用范围：整图 Creator Agent、图片 Judge、后续 PPT Judge 与个性化 Ground Truth 适配

## 1. 文档目的

本文档是 ResearchFigureStudio 后续 Judge Model 研发的单一主路线，用于保证数据生产、标注、训练、评测、部署以及 Creator Agent 协同优化之间保持连续。

后续任何 Judge 相关实验都必须回答以下问题，并将结果回写到本文档的“状态与决策记录”中：

1. 使用了哪个 Ground Truth、数据集版本和模型版本？
2. 改变了什么变量，固定了什么条件？
3. 科学错误召回、审美偏好匹配和候选排序是否提升？
4. 是否通过冻结测试集与反 Reward Hacking 检查？
5. 新模型是否具备替换当前 Bootstrap Judge 的资格？

## 2. 当前状态与问题定义

### 2.1 已完成能力

当前仓库已经实现：

```text
结构化 Ground Truth
→ Creator Agent 生成整图
→ Online Judge 评分并产生 preserve/repair
→ Creator Agent 重新生成或编辑
→ Frozen Judge 独立验收
→ 保存 preference、repair、critique outcome 训练轨迹
```

入口命令为：

```powershell
rfs coevolve-image --ground-truth ground_truth.json --out output/run
```

当前 Judge 实际是通用 VLM Bootstrap：通过 Prompt 调用外部多模态模型，模型权重没有经过本项目训练。

### 2.2 首次真实实验结论

AutoFigure smoke experiment 中：

| 轮次 | Frozen总分 | 科学性 | 审美 | 视觉质量 | 阻塞问题 |
|---|---:|---:|---:|---:|---:|
| 初始图 | 0.425 | 0.40 | 0.30 | 0.80 | 4 |
| 修复图 | 0.765 | 0.85 | 0.65 | 0.75 | 0 |

闭环能够改善图片，但最终图仍虚构了 `Encoder`、`Prediction`、`Ranking`、`Top-1` 等与论文方法无关的模块，Bootstrap Frozen Judge 却判断不存在阻塞问题。

因此当前最关键的问题不是评分精度，而是：

> Judge 对“美观但科学错误”的图片存在高风险漏检，不能承担自动批准职责。

### 2.3 Judge 的最终定义

本项目中的 Judge 不是单一总分回归器，而是一个 Ground Truth 条件化的多任务评价系统：

```text
Trained Multimodal Judge
    ├── 科学事实与关系核验
    ├── 人类审美偏好匹配
    ├── 视觉质量与可读性评价
    ├── 候选图片成对排序
    ├── 错误区域与证据定位
    └── 修改建议有效性预测

Deterministic Grounding Gate
    ├── OCR与术语检查
    ├── 实体/关系覆盖检查
    ├── 禁止内容检查
    └── 硬约束门禁

Score Aggregator
    └── 根据Ground Truth权重计算总分和通过状态
```

训练后的 VLM 是核心 Judge Model；Grounding Gate 是防止漏检和 Reward Hacking 的必要安全层。任何模型总分都不能覆盖硬约束失败。

## 3. 最终目标与成功标准

### 3.1 产品目标

用户输入：

```text
论文事实 Ground Truth
+ 人类审美 Ground Truth
+ 正面/负面参考图
+ 输出约束
```

系统能够训练或适配一个专属 Judge Profile，并用该 Judge 指导 Creator Agent，稳定生成符合用户事实标准和审美偏好的科研图。

### 3.2 Judge v1 上线硬指标

Judge v1 进入协同闭环前必须同时满足：

| 指标 | 最低门槛 |
|---|---:|
| 科学硬错误召回率 | ≥ 95% |
| 科学硬错误漏检率 | ≤ 5% |
| 美观但错误对抗集拦截率 | ≥ 95% |
| Pairwise候选排序准确率 | ≥ 80% |
| 审美偏好排序准确率 | ≥ 75% |
| 修改建议有效率 | ≥ 70% |
| 重复评分标准差 | ≤ 0.03 |
| 新论文跨领域排序准确率 | ≥ 70% |
| 结构化JSON合法率 | ≥ 99% |

Judge v1 不满足科学硬错误指标时，不允许通过调低阈值上线。

### 3.3 协同优化成功标准

使用训练后的 Judge 后，Creator 协同循环应满足：

- 相比单次生成，最终冻结测试得分显著提升；
- 达标率提高，平均迭代轮数下降；
- 科学错误不随迭代增加；
- 审美多样性不因优化而坍缩成单一模板；
- Judge 建议在独立验证下确实改善目标维度；
- Agent 无法通过删除信息、堆叠关键词或模仿评分器格式骗取高分。

## 4. Ground Truth 与数据契约

### 4.1 Ground Truth 是所有训练的最高权威

Ground Truth 包含：

```text
GroundTruthPack
├── paper_path
├── scientific_truth
│   ├── figure_goal
│   ├── entities/modules
│   ├── relations
│   ├── must_show
│   ├── must_not_invent
│   ├── terminology
│   └── evidence
├── aesthetic_preferences
│   ├── natural_language_preferences
│   ├── positive_references
│   ├── negative_references
│   ├── layout_preferences
│   ├── color_preferences
│   └── forbidden_styles
├── weights
└── thresholds
```

人类审美反馈只通过 Ground Truth、参考图和离线偏好标注进入系统，不在在线生成过程中临时改变标准。

### 4.2 Judge 训练样本统一格式

所有训练任务统一转换为 `JudgeExample`：

```json
{
  "example_id": "stable-id",
  "dataset_version": "judge-dataset-v001",
  "ground_truth_id": "gt-id",
  "ground_truth_path": "...",
  "task_type": "single_score|pairwise_rank|error_audit|critique|critique_outcome",
  "candidate_a": "image-a.png",
  "candidate_b": "image-b.png",
  "labels": {
    "scientific_score": 0.0,
    "aesthetic_score": 0.0,
    "visual_quality_score": 0.0,
    "blocking_issues": [],
    "grounded_entities": [],
    "ungrounded_entities": [],
    "missing_relations": [],
    "incorrect_relations": [],
    "preferred_candidate": "A|B|tie",
    "preserve": [],
    "repair": [],
    "confidence": 0.0
  },
  "provenance": {
    "generator_model": "...",
    "bootstrap_judge": "...",
    "human_audited": false,
    "source_run": "..."
  }
}
```

### 4.3 Critique Outcome 格式

Judge 的建议必须通过修改结果获得反馈：

```json
{
  "before_image": "...",
  "critique": [],
  "after_image": "...",
  "target_dimensions": [],
  "score_deltas": {},
  "new_blocking_issues": [],
  "feedback_effective": true,
  "human_or_frozen_validation": "..."
}
```

“建议有效”不能仅由产生该建议的 Judge 自己决定。

## 5. 数据建设路线

### 5.1 数据来源

训练数据由五类来源组成：

1. **真实生成轨迹**：当前 `coevolve-image` 产生的候选、反馈与修改前后图片。
2. **Ground Truth 正例**：论文原图、用户认可图、人工确认的最终图。
3. **生成负例**：不同模型、不同 Prompt、不同迭代轮次产生的失败图。
4. **可控合成错误**：对正确图片主动制造已知错误。
5. **审美偏好对**：同一科学内容下，不同风格和布局的 A/B 选择。

### 5.2 必须覆盖的合成错误

每个 Ground Truth 至少生成以下硬负例：

- 删除一个核心模块；
- 添加论文不存在的模块；
- 反转一条关键箭头；
- 交换训练和推理阶段；
- 替换一个核心术语；
- 保持美观但改变科学事实；
- 保持科学正确但严重降低可读性；
- 使用错误审美风格；
- 复制正向参考图风格但加入虚构内容；
- 通过减少信息获得更高视觉简洁度。

合成错误必须记录注入位置和预期标签，使其成为可靠的科学错误监督数据。

### 5.3 数据规模阶段

#### D0：协议验证集

- 30–50个 Ground Truth；
- 每个 Ground Truth 生成4–8张候选；
- 至少500个单图评价样本；
- 至少500个 Pairwise 样本；
- 所有科学硬错误样本人工复核。

目标：验证数据契约、标注流程和基线指标，不用于正式上线。

#### D1：Judge v1 训练集

- 300–500个 Ground Truth；
- 3,000–5,000张真实或合成图片；
- 8,000–15,000个多任务训练记录；
- 科学错误、审美偏好、视觉质量样本保持基本平衡；
- 至少20%的样本经过人工审计；
- 所有高置信度上线测试样本必须经过人工审计。

#### D2：个性化与跨领域集

- 新论文领域；
- 不同用户审美 Profile；
- 中英文与混合术语；
- 不同图类型：pipeline、taxonomy、system、training/inference、dataset overview；
- 后续 PPT 可编辑性任务。

### 5.4 数据集切分

必须按 Ground Truth/论文进行切分，禁止同一论文的不同图片跨训练集和测试集：

```text
train: 70%
validation: 15%
hidden_test: 15%
```

另设不可参与调参的对抗测试集：

```text
beautiful_but_wrong
correct_but_ugly
relation_reversal
missing_core_stage
invented_module
terminology_corruption
style_preference_conflict
reward_hacking
```

### 5.5 标注流程

```text
Bootstrap VLM预标注
→ Grounding Gate自动检查
→ 人工审计硬错误与A/B偏好
→ 冲突样本二次裁决
→ 写入数据版本
→ 冻结后生成hash与manifest
```

标注者不能只看到图片，必须同时看到 Ground Truth 和论文证据摘要。

## 6. Judge 模型技术路线

### 6.1 首版不从零训练

Judge v1 使用开源多模态指令模型作为共享 Backbone，通过 LoRA/QLoRA 完成多任务适配。首版不进行全参数微调。

Backbone 在训练前通过固定 D0 bake-off 选择，候选应满足：

- 可同时读取长 Ground Truth 和高分辨率科研图；
- 支持多图 Pairwise 输入；
- 结构化 JSON 输出稳定；
- 允许本地或受控环境微调；
- 7B–10B 参数规模优先，以控制迭代成本。

Backbone 选择一旦写入某个数据/实验版本，在该版本全部消融实验结束前不得更换。

### 6.2 多任务训练顺序

#### Stage A：结构化输出 SFT

训练任务：

- 单图分项评分；
- Ground Truth 证据引用；
- 实体和关系核验；
- blocking issue 识别；
- preserve/repair 生成；
- JSON 协议遵循。

目标：让模型首先学会稳定、可解析、可追溯地评价，而不是追求总分相关性。

#### Stage B：Pairwise 排序训练

输入同一 Ground Truth 下的 A/B 图片，训练模型选择：

```text
A优于B
B优于A
Tie
```

Pairwise 训练优先于绝对分数回归，因为人类审美和综合质量的相对判断更稳定。

#### Stage C：硬错误强化

提高以下样本的损失权重：

- 美观但科学错误；
- 新增不存在模块；
- 关键关系反转；
- 核心内容遗漏；
- 术语错误；
- Judge 高分但人工判定不可接受的历史失败样本。

科学阻塞判断使用高召回优先策略，宁可产生可审查的假阳性，也不能轻易漏掉严重错误。

#### Stage D：建议有效性训练

输入：原图片、Critique、修改后图片和结果标签。

训练模型预测：

- 建议是否可执行；
- 目标维度是否可能提升；
- 是否可能破坏已有正确内容；
- 应采用局部编辑还是整图重生成。

#### Stage E：分数校准

在模型训练完成后，使用独立验证集校准分数和置信度。总分由代码根据 Ground Truth 权重计算，模型只输出分项分数，禁止模型自行决定权重。

### 6.3 默认训练方式

- 首选 QLoRA 进行第一轮验证；
- 固定随机种子并记录 CUDA、依赖和显卡信息；
- 保存每个 epoch 的 checkpoint，但仅保留验证门禁最优版本为候选；
- 使用 gradient accumulation 支持单机训练；
- 7B级模型建议至少24–48GB显存进行 QLoRA；
- 正式实验建议使用48GB以上显存或多卡；
- 不允许只报告训练 loss，必须报告隐藏集指标。

## 7. Grounding Gate 技术路线

训练模型之外必须实现独立 Grounding Gate。

### 7.1 输入

- Ground Truth 实体与关系；
- 候选图片；
- OCR 文本；
- VLM 提取的图中实体、模块和箭头关系；
- 必须展示与禁止内容列表。

### 7.2 输出

```json
{
  "grounded_entities": [],
  "ungrounded_entities": [],
  "missing_required_entities": [],
  "grounded_relations": [],
  "incorrect_relations": [],
  "terminology_errors": [],
  "blocking_issues": [],
  "gate_pass": false
}
```

### 7.3 门禁规则

以下情况直接失败，不参与软分加权：

- 关键模块缺失；
- 新增具有科学含义但无法映射到 Ground Truth 的模块；
- 关键关系方向错误；
- 命中 `must_not_invent`；
- 核心术语被替换或严重拼写错误；
- Judge 无法为高置信度科学判断提供 Ground Truth 依据。

## 8. 评测体系

### 8.1 必须保留的基线

每次 Judge 训练都与以下基线比较：

1. 当前通用 VLM Bootstrap Judge；
2. 未微调 Backbone；
3. 仅 SFT Judge；
4. SFT + Pairwise Judge；
5. 完整 Judge + Grounding Gate。

### 8.2 核心指标

#### 科学性

- blocker precision/recall/F1；
- invented entity recall；
- missing entity recall；
- relation direction accuracy；
- terminology error recall；
- evidence attribution accuracy。

#### 审美与综合质量

- Pairwise accuracy；
- 与 Ground Truth 人类偏好的 Spearman/Kendall 相关性；
- 风格正例/负例识别准确率；
- 不同审美 Profile 的区分能力。

#### 反馈质量

- repair instruction 可执行率；
- 修改后目标维度提升率；
- 修改导致新科学错误的比例；
- preserve 内容保持率。

#### 稳定性

- 同图重复评分方差；
- 候选顺序随机化一致性；
- 图片轻微压缩/缩放后的评分稳定性；
- 不同领域与不同图类型上的泛化。

### 8.3 必做消融实验

- 去掉 Grounding Gate；
- 去掉合成错误数据；
- 去掉 Pairwise 训练；
- 去掉审美参考图；
- 只使用自然语言审美偏好；
- 去掉 Critique Outcome 训练；
- 科学错误样本不加权；
- Online/Frozen 使用同一模型；
- 不同 Backbone；
- 不同 LoRA rank 与数据规模。

## 9. 模型版本与上线门禁

### 9.1 版本命名

```text
judge-bootstrap-v0
judge-sft-v1.0
judge-pairwise-v1.1
judge-grounded-v1.2
judge-profile-<user>-v1
```

每个模型版本必须绑定：

- Backbone 和 checkpoint；
- 数据集版本与 hash；
- 训练配置；
- Git commit；
- 评测报告；
- 已知失败类型；
- 可用于 Online、Frozen 或仅实验的角色声明。

### 9.2 上线流程

```text
离线训练
→ validation选择候选
→ hidden_test评测
→ 对抗测试
→ Shadow Judge运行
→ 与当前Judge分歧分析
→ 小流量Online Judge
→ Frozen Gate仍使用旧稳定版本
→ 达标后升级Frozen Judge
```

新 Judge 不得同时替换 Online 和 Frozen。必须先作为 Shadow 或 Online Judge 运行，Frozen Judge 保持旧版本；经过稳定期后才能成为新的 Frozen Judge。

### 9.3 回滚条件

出现以下情况立即回滚：

- 科学硬错误漏检率超过门槛；
- Judge 与人工审计发生系统性偏差；
- JSON 合法率下降；
- 分数漂移导致大量历史样本阈值变化；
- Creator 生成结果趋同或明显 Reward Hacking；
- 新 Judge 使最终图科学性下降，即使综合分提高。

## 10. 与 Creator Agent 的协同训练

### 10.1 Judge 先于 Creator 训练

Creator Agent 不得使用未经门禁的 Judge 奖励进行权重训练。固定顺序为：

```text
训练并冻结 Judge v1
→ 用 Judge v1 重新评分历史轨迹
→ 筛选成功 Repair Trajectory
→ Creator SFT
→ Creator Pairwise/DPO
→ 冻结测试集验证
→ 产生新轨迹
→ 构建 Judge v2 数据，但不直接在线互相更新
```

### 10.2 Creator 训练数据

#### SFT

```text
Ground Truth
+ 原图片
+ Judge preserve/repair
→ 成功设计计划与生成 Prompt
```

#### DPO/Pairwise

```text
chosen: 通过Grounding Gate且冻结得分更高的图片/Prompt
rejected: 科学错误、审美不符或修改无效的图片/Prompt
```

### 10.3 交替升级规则

Judge 与 Creator 可以交替升级，但不能在同一周期同时改变后直接互相证明成功。

每个周期固定：

1. 冻结 Judge；
2. 更新 Creator；
3. 在旧隐藏集评估 Creator；
4. 收集新 Creator 的失败模式；
5. 冻结 Creator；
6. 更新 Judge；
7. 在固定图片集上评估 Judge；
8. 两者分别通过门禁后才进入下一周期。

## 11. 个性化 Ground Truth 适配

Judge v1 首先学习通用科学严谨性与通用审美评价。用户个性化只调整审美相关能力，不允许覆盖科学硬门禁。

### 11.1 三档适配

#### 零样本 Profile

- 输入自然语言偏好和正负参考图；
- 不更新模型权重；
- 使用 Ground Truth 条件化和参考图检索。

#### 少样本 Profile

- 20–100组成对偏好；
- 训练轻量审美 Adapter 或 Preference Head；
- 共享科学 Grounding Backbone。

#### 完整 Profile

- 数百至数千偏好和生成轨迹；
- 训练用户专属审美 Adapter；
- 使用通用科学门禁和用户审美头组合评分。

### 11.2 权限边界

用户审美偏好可以改变：

- 风格；
- 配色；
- 布局密度；
- 视觉隐喻；
- 创新程度；
- 信息层级。

用户审美偏好不能改变：

- 论文事实；
- 模块和关系真实性；
- 禁止虚构规则；
- 关键术语准确性；
- 科学阻塞门槛。

## 12. 后续 PPT Judge 扩展

图片 Judge 稳定后再扩展 PPT Judge。PPT Judge 共享科学与审美 Backbone，但增加：

- 目标图片与 PPT 渲染图的视觉还原；
- PPT 对象树输入；
- 文本、箭头、公式和分组的可编辑性；
- 对象坐标和层级问题定位；
- PPT 修复建议有效性。

PPT Judge 不应在图片 Judge 尚未通过科学门禁前开始正式训练，否则会把错误目标图片忠实地转换成错误 PPT。

## 13. 工程实施路线

### Phase 0：冻结协议与基线

输入：当前 coevolution 输出。  
工作：固定 Ground Truth、JudgeExample、CritiqueOutcome 和评测协议。  
输出：`judge-dataset-schema-v1`、Bootstrap 基线报告。  
门禁：所有样本可追溯，协议单测通过。

### Phase 1：D0 数据与 Grounding Gate

输入：30–50个 Ground Truth。  
工作：真实生成、合成错误、人工审计、实体关系门禁。  
输出：D0 数据、对抗集、Grounding Gate v0。  
门禁：已知注入错误召回率≥95%。

### Phase 2：Backbone Bake-off

输入：冻结 D0。  
工作：比较2–3个7B–10B多模态 Backbone。  
输出：模型比较报告和固定 Backbone 决策。  
门禁：JSON稳定性、科学召回和多图能力达到最低要求。

### Phase 3：Judge SFT 与 Pairwise

输入：D1 train/validation。  
工作：Stage A–C 训练。  
输出：Judge候选 checkpoint。  
门禁：validation 全部核心指标达标。

### Phase 4：建议有效性与校准

输入：Repair Trajectory 和 Critique Outcome。  
工作：Stage D–E 训练与置信度校准。  
输出：Judge v1 release candidate。  
门禁：建议有效率≥70%，分数稳定性达标。

### Phase 5：隐藏集与 Shadow 部署

输入：隐藏集、对抗集、真实在线任务。  
工作：与 Bootstrap Judge 并行运行但不控制 Creator。  
输出：分歧分析和失败案例库。  
门禁：科学漏检率≤5%，无系统性退化。

### Phase 6：接管 Online Judge

输入：通过门禁的 Judge v1。  
工作：指导 Creator，但旧稳定 Judge 继续担任 Frozen Judge。  
输出：真实协同轨迹。  
门禁：最终图质量提升且科学错误不增加。

### Phase 7：接管 Frozen Judge

输入：稳定运行后的 Judge v1。  
工作：升级冻结门禁并保留旧模型回滚能力。  
输出：正式 Judge v1。  
门禁：完整回归、对抗和人工抽查通过。

### Phase 8：训练 Creator Agent

输入：Judge v1 重新验证的成功轨迹。  
工作：SFT、DPO和协同循环评测。  
输出：Creator v1。  
门禁：更少迭代达到更高冻结分数，无多样性坍缩。

### Phase 9：个性化与 PPT Judge

输入：用户偏好和已批准目标图片。  
工作：审美 Adapter、PPT 可编辑性评价。  
输出：用户 Judge Profile 和 PPT Judge。  
门禁：个性化提升不破坏通用科学门禁。

## 14. 计划中的工程接口

后续 CLI 统一规划为：

```powershell
# 构建数据
rfs judge-data build --runs output/runs --out datasets/judge-v001

# 注入可控错误
rfs judge-data corrupt --dataset datasets/judge-v001 --out datasets/judge-v001-corrupted

# 校验与冻结数据版本
rfs judge-data validate --dataset datasets/judge-v001 --freeze

# 训练
rfs judge train --config configs/judge_sft_v1.json

# 离线评测
rfs judge evaluate --checkpoint models/judge-v1 --suite hidden_test

# 对抗评测
rfs judge evaluate --checkpoint models/judge-v1 --suite adversarial

# Shadow运行
rfs coevolve-image --judge-checkpoint models/judge-v1 --judge-mode shadow

# 正式Online Judge
rfs coevolve-image --online-judge-checkpoint models/judge-v1
```

建议的仓库目录：

```text
rfs/judge_training/
├── schemas.py
├── dataset_builder.py
├── corruption_generator.py
├── grounding_gate.py
├── trainer.py
├── evaluator.py
├── calibration.py
└── registry.py

configs/judge/
datasets/                 # gitignored
models/                   # gitignored
experiments/judge/        # 配置、指标和报告；不包含私有图片
```

## 15. 实验记录标准

每个训练或评测实验必须保存：

```text
experiment_id/
├── objective.md
├── config.json
├── environment.json
├── dataset_manifest.json
├── model_manifest.json
├── metrics.json
├── error_buckets.json
├── qualitative_examples/
├── conclusion.md
└── next_actions.md
```

实验结论必须包含：

- 实验问题；
- 改变的变量；
- 固定条件；
- 数据规模和切分；
- 主要指标；
- 置信区间或重复实验结果；
- 最强结论；
- 最大不确定性；
- 是否允许模型升级。

## 16. 风险与防护

### Reward Hacking

风险：Creator 学会迎合 Judge 而不是 Ground Truth。  
防护：独立 Grounding Gate、冻结对抗集、不同 Online/Frozen 版本、人工抽查。

### Judge–Creator 共谋漂移

风险：两者通过彼此生成的数据共同偏离。  
防护：交替冻结训练、旧隐藏集、模型升级分离、禁止同周期互证。

### 审美模板坍缩

风险：所有图片趋向相同布局和配色。  
防护：多审美 Profile、风格多样性指标、不同参考图条件化。

### 科学错误被总分掩盖

风险：审美高分抵消科学错误。  
防护：硬错误直接 gate fail，科学阻塞不参与加权抵消。

### 数据泄漏

风险：同一论文或参考图进入训练和测试。  
防护：按 Ground Truth ID 切分，图像感知哈希去重，冻结 manifest。

### 私有论文与图片泄漏

风险：用户材料进入仓库或外部服务。  
防护：数据和模型目录 gitignore；记录数据许可；支持本地训练和本地 Judge。

## 17. 状态与决策记录

所有后续重大决策追加到本节，不覆盖历史记录。

| 日期 | 决策 | 原因 | 影响 |
|---|---|---|---|
| 2026-07-15 | 当前 Gemini Judge 定义为 Bootstrap Judge，而非已训练 Judge | 权重未更新，仅通过 Prompt 评价 | 只能用于数据生产和基线 |
| 2026-07-15 | Judge v1 使用“训练VLM + Grounding Gate + 代码聚合” | 首次真实实验出现科学幻觉漏检 | 科学硬错误不能依赖单一总分 |
| 2026-07-15 | 先训练和冻结 Judge，再训练 Creator | 避免不稳定奖励污染 Agent | Judge 门禁成为 Creator 训练前置条件 |
| 2026-07-15 | Online/Frozen 不允许同步升级 | 防止模型自证成功 | 采用 Shadow→Online→Frozen 顺序 |

## 18. 立即执行清单

后续工作从以下顺序开始，不跳步：

1. 实现 `JudgeExample` 和数据集 manifest schema；
2. 将现有 `preference_pairs.jsonl`、`repair_trajectories.jsonl`、`critique_outcomes.jsonl` 转换为统一格式；
3. 实现 Grounding Gate v0，首先覆盖 OCR术语、实体、缺失模块和虚构模块；
4. 建立 `beautiful_but_wrong` 对抗集，并纳入 AutoFigure 首次实验失败图；
5. 准备30–50个结构化 Ground Truth，生成 D0；
6. 完成人工审计界面或审计表；
7. 冻结 D0 后进行 Backbone bake-off；
8. Backbone 确定后才引入 LoRA/QLoRA 训练依赖；
9. Judge v1 通过隐藏集后，以 Shadow 模式接入当前闭环；
10. Judge 稳定后再启动 Creator 权重训练和 PPT Judge。

## 19. 阶段完成定义

本路线的 Judge 阶段只有在以下条件全部满足后才算完成：

- 训练出的模型 checkpoint 可复现；
- 数据、配置、Git commit 和指标完整绑定；
- 科学硬错误漏检率达到门槛；
- 对抗集和跨领域测试通过；
- Shadow 和 Online 阶段未出现系统性退化；
- Creator 协同优化在冻结测试中得到真实提升；
- 旧模型可随时回滚；
- 个性化审美不会覆盖科学硬约束。

在此之前，任何通用 VLM Prompt Judge 都只能称为 Bootstrap Judge，不能称为“项目训练出的 Judge Model”。
