一、最终系统目标
用户输入：
论文
+ 审美偏好
+ 正面/负面参考图（可选）
+ 输出与可编辑性要求
系统自动完成：
Ground Truth 构建
→ 论文信息检索
→ 科研图规划
→ Image2 生成
→ 图片评价与反复改进
→ 合格科研图片
→ 图片转可编辑 PPTX
→ PPT 评价与反复修复
→ 最终可编辑科研图
未来进一步支持：
用户 Ground Truth
→ 自动构造训练数据
→ 训练/适配用户专属评价模型
→ 训练/适配用户专属制图 Agent
→ 导出可复用的 Figure Profile
二、Ground Truth 设计
Ground Truth 不只是论文文件，而是一个完整的目标包。
ground_truth/
├── paper/
│   └── paper.pdf
├── scientific_truth.yaml
├── aesthetic_preferences.yaml
├── output_constraints.yaml
├── positive_references/
├── negative_references/
├── pairwise_preferences.jsonl
└── terminology.json
1. 论文事实标准
scientific_truth.yaml 可以由系统从论文中自动提取，再进行校验：
figure_goal: 展示模型从输入到输出的完整方法流程

must_show:
  - 输入数据
  - 特征编码器
  - 推理模块
  - 训练目标
  - 最终输出

core_modules:
  - id: encoder
    name: Feature Encoder
    evidence: Section 3.1

relations:
  - source: encoder
    target: reasoning_module
    type: feature_flow
    evidence: Section 3.2

must_not_invent:
  - 论文没有使用强化学习
  - 不得添加不存在的外部知识库

terminology:
  Feature Encoder: 必须使用该英文名称
每个重要事实都要绑定论文证据，避免评价模型和 Agent 自行补充不存在的方法。
2. 人类审美标准
aesthetic_preferences.yaml 应同时支持自然语言、参数化偏好和参考图片：
overall_style:
  description: >
    顶会论文风格，精致、现代、信息丰富，但不能像商业宣传海报。
  preferred_styles:
    - clean academic illustration
    - restrained 2.5D
    - dense but readable
  forbidden_styles:
    - cartoon
    - cyberpunk
    - excessive gradients
    - generic dashboard cards

layout:
  preferred_flow: left_to_right
  symmetry: moderate
  visual_density: high
  whitespace: moderate
  hierarchy_strength: strong

colors:
  preferred_palette:
    - blue
    - teal
    - warm orange accent
  saturation: low_to_medium
  avoid:
    - neon colors
    - large dark backgrounds

visual_elements:
  prefer:
    - concrete visual metaphors
    - layered scientific objects
    - clear module boundaries
  avoid:
    - standalone generic icons
    - repeated identical cards
    - decorative objects without meaning

innovation:
  desired_level: 0.75
  description: >
    允许创造新的视觉隐喻和布局，但不能改变论文逻辑。

references:
  positive:
    - positive_references/figure_01.png
  negative:
    - negative_references/figure_01.png
审美偏好可以来自四类输入：
用户自然语言描述；
用户提供的优秀参考图；
用户提供的反例；
用户预先完成的 A/B 图片选择。
这些都属于 Ground Truth，不是在生成过程中临时获得的反馈。
3. 输出约束
image:
  aspect_ratio: "16:9"
  min_resolution: [1920, 1080]
  readable_text: true

pptx:
  editable_text_required: true
  editable_arrows_required: true
  editable_groups_required: true
  max_flattened_area_ratio: 0.35

hard_thresholds:
  scientific_fidelity: 0.95
  relation_correctness: 0.95
  terminology_accuracy: 1.0
  aesthetic_preference: 0.80
三、总体系统架构
系统分为九个核心模块：
Ground Truth Compiler
        ↓
Paper Retrieval Agent
        ↓
Scientific Figure Specification
        ↓
Figure Creation Agent
        ↓
Image Evaluator
        ↓
Image Evolution Orchestrator
        ↓
Image-to-PPTX Converter
        ↓
Editable PPT Evaluator
        ↓
PPT Evolution Orchestrator
训练系统位于闭环之外：
所有生成轨迹
→ Training Dataset Builder
→ Evaluator Trainer
→ Agent Trainer
→ Model Registry
四、第一阶段：Ground Truth Compiler
任务
将用户输入的论文、审美描述、参考图和约束编译成机器可执行标准。
输出
compiled_ground_truth.json
scientific_rubric.json
aesthetic_rubric.json
hard_constraints.json
reference_embedding_index/
ground_truth_validation_report.json
必须解决的问题
审美描述是否存在矛盾；
正面参考图之间是否风格冲突；
审美要求是否影响科学表达；
哪些条件是硬约束，哪些是软偏好；
各个评价维度的权重是多少。
验收条件
每条科学要求有论文证据；
每项审美偏好可以转化为评价维度；
硬约束和软约束明确分离；
同一个 Ground Truth 多次编译结果稳定。
五、第二阶段：论文信息检索
这是目前需要重点补齐的第一块能力。
工作流程
论文解析
→ 章节切分
→ 公式、表格、图注提取
→ 实体和模块识别
→ 方法关系图构建
→ 证据检索
→ 一致性检查
→ Figure Specification
输出的 Figure Specification
{
  "figure_goal": "...",
  "storyline": [],
  "modules": [],
  "relations": [],
  "training_flow": [],
  "inference_flow": [],
  "innovations": [],
  "inputs": [],
  "outputs": [],
  "visual_priorities": [],
  "forbidden_inventions": [],
  "evidence_map": {}
}
技术策略
第一版不需要训练检索模型，可以使用：
PDF 内容解析；
分章节索引；
混合关键词与向量检索；
LLM/VLM 结构化抽取；
多次证据回查；
关系图一致性验证。
验收指标
核心模块召回率；
模块关系准确率；
论文创新点覆盖率；
无证据内容比例；
专有术语准确率。
科学事实错误应该被视为硬失败，不能由审美高分抵消。
六、第三阶段：科研制图 Agent V0
Agent 不能直接从论文生成 prompt，而应该分层工作。
Figure Specification
→ 信息叙事规划
→ 布局草案
→ 视觉隐喻设计
→ 风格计划
→ Image2 Prompt
→ 图片生成
每轮必须保存：
design_plan.json
layout_intent.json
visual_metaphors.json
image2_prompt.txt
generation_parameters.json
generated_image.png
Agent 接收上一轮反馈时，应将其转化为 Repair Plan：
{
  "preserve": [
    "保持左侧输入区域",
    "保持整体配色"
  ],
  "repair": [
    "补充模块B到模块C的关系",
    "强化核心创新模块的视觉层级"
  ],
  "remove": [
    "删除论文中不存在的数据库图标"
  ],
  "regeneration_scope": "middle_and_right_regions"
}
即使 Image2 只能重新生成整张图片，也要明确告诉它哪些内容必须保留，避免每轮完全漂移。
七、第四阶段：图片评价模型
评价模型输入：
论文 Ground Truth
+ 审美 Ground Truth
+ Figure Specification
+ Agent 设计计划
+ 当前生成图片
+ 历史版本
评价结果分为三层。
1. 硬约束判断
是否存在论文事实错误；
是否遗漏核心模块；
是否生成不存在的机制；
箭头方向是否错误；
术语是否错误；
是否违反用户禁止项。
任何严重问题都直接阻止通过。
2. 分维度评分
{
  "scientific_fidelity": 0.96,
  "information_completeness": 0.87,
  "relation_correctness": 0.93,
  "aesthetic_preference": 0.82,
  "visual_hierarchy": 0.78,
  "style_consistency": 0.88,
  "innovation": 0.73,
  "readability": 0.84
}
3. 可执行反馈
评价模型必须输出：
问题位置；
问题类别；
严重程度；
Ground Truth 依据；
应保留内容；
应修改内容；
禁止引入的副作用；
推荐的下一轮生成策略。
单独输出“总分75，布局需要优化”没有训练和执行价值。
八、评价模型如何获得反馈
由于人类偏好已经放入 Ground Truth，闭环中不再实时询问人类。评价模型的反馈来源改为以下四类。
1. Ground Truth 一致性反馈
检查评价结果是否正确引用了：
论文证据；
人类审美规则；
正面参考图；
负面参考图；
输出硬约束。
如果评价模型提出一条没有 Ground Truth 支撑的要求，应视为评价错误。
2. 修改结果反馈
评价模型提出修改后，比较新旧图片：
评价模型指出问题
→ Agent 修改
→ 新图片产生
→ 独立比较器判断问题是否改善
形成如下训练记录：
{
  "critic_claim": "核心创新模块视觉层级不足",
  "predicted_improvement": ["visual_hierarchy"],
  "before_score": 0.68,
  "after_score": 0.81,
  "side_effects": [],
  "feedback_effective": true
}
这是评价模型最重要的结果反馈：它的建议有没有真正产生更好的结果。
3. 独立工具反馈
使用独立工具校准评价模型：
OCR：检查术语和乱码；
图结构解析：检查模块和箭头；
文本检索：验证论文证据；
图像布局分析：检查遮挡、对齐和留白；
参考图相似度：检查审美偏好；
多模型交叉评价：检查单一 Evaluator 偏差。
4. 稳定性反馈
同一张图重复评价时：
分数是否稳定；
错误定位是否一致；
轻微图像扰动是否导致评分剧烈变化；
模块顺序被故意破坏后是否能够发现；
美观但科学错误的图片是否会被错误放行。
九、第五阶段：图片自进化循环
循环逻辑：
生成候选
→ 评价
→ 选择最佳候选
→ 产生 Repair Plan
→ 再生成
→ 比较新旧版本
→ 更新轨迹
→ 判断是否停止
每轮建议生成 2～4 个候选，而不是只生成一张。
停止条件
建议同时满足：
无科学硬错误
AND 科学忠实度 ≥ 0.95
AND 关系正确率 ≥ 0.95
AND 审美偏好 ≥ 0.80
AND 总分 ≥ 0.85
AND 连续两轮提升 < 0.02
AND 两个独立评价结果基本一致
同时设置：
最大迭代轮数；
最大 API 成本；
最大失败次数；
连续退化自动回滚；
保留历史最佳版本。
不能默认使用“最后一轮”，而应该使用“全历史最高且通过硬约束的版本”。
十、第六阶段：接入现有图片转 PPTX 能力
图片阶段达标后，冻结目标图：
approved_image.png
approved_image_spec.json
approved_image_scores.json
然后进入现有转换流程：
目标图结构解析
→ 元素定位
→ 图片区域拆分
→ OCR 与文本重建
→ 箭头和连接关系重建
→ PPT 对象组装
→ PPTX
这一阶段不再重新设计科研图，目标是：
最大程度保持目标图片的视觉表现，同时提升对象级可编辑性。

十一、第七阶段：PPT 自进化循环
PPT 评价模型同时读取：
已批准的目标图片；
当前 PPT 渲染图；
PPT 内部对象树；
文本框；
图片对象；
箭头和连接线；
分组关系；
图层顺序。
PPT 评价指标
视觉还原
整体布局相似度；
模块位置误差；
颜色误差；
文本位置误差；
箭头路径误差；
局部元素缺失率；
渲染前后风格差异。
可编辑性
可编辑文本比例；
可编辑箭头比例；
可独立移动对象比例；
正确分组比例；
整图位图覆盖比例；
对象命名和层级质量；
修改局部元素是否会破坏整体结构。
PPT Agent 可执行动作
调整对象坐标；
修改尺寸和层级；
重建文本框；
重建箭头；
修改字体、颜色和边框；
重新分组；
替换局部图片块；
修复遮挡；
调整连接线控制点。
每轮修改后：
PPTX
→ 重新渲染
→ 与目标图片比较
→ 检查对象可编辑性
→ 产生下一轮修复
PPT 停止条件
视觉还原分 ≥ 0.90
AND 关键文本可编辑率 = 100%
AND 关键箭头可编辑率 = 100%
AND 主要模块可独立编辑
AND 不存在严重遮挡或缺失
AND 连续两轮提升趋于稳定
十二、第八阶段：训练评价模型
不要一开始就直接训练大模型。建议按三个版本演进。
Evaluator V0：组合评价器
由以下模块组成：
强 VLM 评价；
论文证据检索；
OCR；
图结构检查；
审美参考图相似度；
规则验证器。
这一版主要用于跑通全过程和积累数据。
Evaluator V1：专用评分模型
使用 V0 产生的数据，加上人工预先写入 Ground Truth 的偏好数据训练：
分项评分；
图片成对排序；
错误类别识别；
问题区域定位；
建议有效性预测。
训练重点不是拟合绝对分数，而是：
A 是否比 B 更符合 Ground Truth
成对排序通常比绝对打分更稳定。
Evaluator V2：用户定制适配
用户输入自己的审美 Ground Truth 后：
编码用户审美描述；
检索对应参考图；
使用少量 pairwise 数据训练 Adapter；
保留通用科学严谨性能力；
替换或调整审美评价头。
科学评价层尽量共享，审美层允许用户定制。
十三、第九阶段：训练制图 Agent
Agent V0
暂不训练，通过：
系统提示词；
Ground Truth 检索；
优秀案例检索；
结构化 Repair Plan；
多候选生成。
Agent V1：监督微调
训练数据来自成功轨迹：
Ground Truth
+ Figure Specification
+ 上一版图片
+ 评价反馈
→ 正确的设计计划和生成 Prompt
Agent V2：偏好优化
使用同一轮中的好坏候选：
chosen: 更符合 Ground Truth 的方案
rejected: 得分较低的方案
进行 DPO 或类似的偏好训练。
Agent V3：强化优化
只有评价模型经过充分校准后，再考虑基于奖励的训练。否则非常容易出现 reward hacking，例如：
图变得越来越相似但失去创新性；
为了避免错误而删除大量信息；
过度迎合评价模型喜欢的固定布局；
视觉复杂但实际内容错误。
十四、数据与轨迹协议
每次完整运行都应保存：
runs/<run_id>/
├── ground_truth_snapshot/
├── retrieval/
├── figure_specification.json
├── iterations/
│   ├── iter_00/
│   │   ├── design_plan.json
│   │   ├── prompt.txt
│   │   ├── candidates/
│   │   ├── evaluation.json
│   │   └── repair_plan.json
│   └── iter_01/
├── approved_image/
├── ppt_iterations/
├── final.pptx
└── run_summary.json
一个训练样本必须能够追溯：
使用了哪个 Ground Truth；
使用了哪个模型版本；
使用了什么 prompt；
为什么选择这个候选；
评价模型指出了什么；
修改是否有效；
最终是否通过。
十五、评测体系
按照实验规范，必须固定测试条件，避免“看几张图感觉不错”。
数据集切分
以论文为单位划分：
训练集；
验证集；
隐藏测试集；
跨领域测试集；
新审美风格测试集。
同一篇论文不能同时出现在训练和测试中。
核心指标
类别	指标
论文理解	模块召回率、关系准确率、无依据内容率
图片质量	Ground Truth 偏好命中率、科学错误率
评价模型	Pairwise accuracy、评分稳定性、错误定位准确率
反馈质量	建议有效率、平均单轮提升
自进化	达标率、平均迭代轮数、退化率
效率	单图成本、耗时、Image2 调用次数
PPT	视觉还原度、文本/箭头可编辑率
泛化	新论文、新领域、新审美偏好上的性能

必须做以下消融实验：
没有审美 Ground Truth；
只有自然语言审美；
自然语言加正面参考图；
正面和负面参考图同时存在；
没有论文证据回查；
没有历史版本对比；
单 Evaluator 与多 Evaluator；
单候选与多候选；
不同最大迭代轮数。
十六、项目代码实施建议
在当前项目中增加以下模块：
rfs/
├── groundtruth/
│   ├── schema.py
│   ├── compiler.py
│   └── validator.py
├── retrieval/
│   ├── paper_index.py
│   ├── evidence_retriever.py
│   └── figure_spec_builder.py
├── creation_agent/
│   ├── planner.py
│   ├── image2_agent.py
│   └── repair_planner.py
├── evaluators/
│   ├── image_evaluator.py
│   ├── ppt_evaluator.py
│   ├── evidence_checker.py
│   └── preference_scorer.py
├── evolution/
│   ├── image_loop.py
│   ├── ppt_loop.py
│   ├── stopping.py
│   └── trajectory_store.py
├── training/
│   ├── dataset_builder.py
│   ├── evaluator_trainer.py
│   ├── agent_trainer.py
│   └── model_registry.py
└── profiles/
    └── figure_profile.py
现有图片转 PPTX 模块先保留，作为第二个闭环的执行器。
十七、推荐实施顺序
里程碑一：跑通闭环骨架
Ground Truth Schema；
论文信息检索；
Figure Specification；
Agent 生成 Image2；
VLM Evaluator V0；
2～4轮自动迭代；
完整轨迹保存。
验收：至少对10篇论文自动完成论文到达标图片的全过程。
里程碑二：接入 PPT 闭环
冻结达标图片；
接入当前图片转 PPTX；
PPT 渲染对比；
对象级可编辑性检查；
自动坐标和对象修复。
验收：目标图片到 PPTX 的视觉还原和可编辑性均可量化。
里程碑三：建立训练数据
收集多轮轨迹；
构造图片 preference pair；
标注有效和无效的 Critic 建议；
建立训练、验证和隐藏测试集；
实现可复现评测命令。
验收：每个模型版本都有统一 benchmark 报告。
里程碑四：训练 Evaluator
多任务评分；
Pairwise 排序；
错误定位；
反馈有效性预测；
置信度校准。
验收：专用 Evaluator 在隐藏测试集上明显优于纯 VLM Judge。
里程碑五：训练 Agent
成功轨迹 SFT；
好坏方案 DPO；
Ground Truth 条件化；
用户审美 Adapter。
验收：更少迭代次数、更低调用成本达到相同或更高质量。
里程碑六：用户自定义训练产品
最终提供类似接口：
rfs groundtruth compile --config user_groundtruth.yaml

rfs profile train `
  --ground-truth compiled_ground_truth.json `
  --examples user_preferences/ `
  --out profiles/user_style_v1

rfs evolve `
  --paper paper.pdf `
  --profile profiles/user_style_v1 `
  --out output/run_001