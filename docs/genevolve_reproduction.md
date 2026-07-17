# GenEvolve v2 论文级复现路线

论文：**GenEvolve: Self-Evolving Image Generation Agents via Tool-Orchestrated Visual Experience Distillation**  
arXiv:2605.21605v2，2026-05-22  
项目页：https://ephemeral182.github.io/GenEvolve/

## 1. 先澄清：GenEvolve 不是普通 Creator–Judge 图片迭代

论文训练的是一个 `Qwen3-VL-8B-Instruct` 图像生成 Agent。Agent 不直接输出图片，而是在多轮轨迹中决定：

1. 是否调用 `search(q)` 查询可见事实；
2. 如何调用 `image_search(q)` 获取视觉参考；
3. 何时调用 `query_knowledge(skill_name)` 激活内部生成知识；
4. 如何选择 1～2 张参考图；
5. 如何输出可执行的 prompt-reference program `z=(g,R)`；
6. 将程序交给 Qwen-Image-Edit 或 Nano Banana Pro 生成最终图片。

论文的核心训练信号来自同一请求的多条轨迹。系统比较奖励最高和最低的轨迹，将差异总结成结构化视觉经验，并且只把该经验提供给 privileged teacher。Student 在正常推理上下文中运行，通过 token-level SDL 将 teacher 的决策偏好吸收到参数中。

当前仓库的 `rfs coevolve-image` 是一个有用的推理期 Creator/Judge 基线，但没有训练 Agent policy，也没有实现论文的 GRPO 或 SDL，因此不能视为完整 GenEvolve 复现。

## 2. 原文方法的最小模块

### 2.1 Agent 与工具环境

- Backbone：Qwen3-VL-8B-Instruct。
- 工具：`search`、`image_search`、`query_knowledge`。
- 八类生成知识：text、layout、body、style、bind、create、physics、count。
- 每个 assistant turn 只能调用一个工具或提交最终 JSON。
- 最终程序必须选择 1～2 张参考图，并使用“the first reference image”等序数绑定，不能泄露 URL 或临时图片 ID。

### 2.2 SFT cold start

- 8,800 条训练轨迹，200 条 SFT held-out 轨迹。
- 只计算 assistant tokens 的损失；user prompt 与 tool observations 只作为上下文。
- 冻结视觉编码器和多模态 projector，仅训练 language-policy 参数。
- `cutoff_len=32768`，bf16，FlashAttention-2，ZeRO-3。

### 2.3 双奖励 GRPO

每个 prompt 采样 6 条 rollout：

```text
R = 0.5 * R_image + 0.5 * R_text
```

- `R_image`：Gemini 3.1 Pro Preview 按 KScore 评分。
- KScore 权重：Faithfulness 0.1、Visual correctness 0.4、Text accuracy 0.4、Aesthetics 0.1。
- `R_text`：检查 prompt-reference program 是否包含充分的事实、参考绑定、技能知识与可执行约束。
- GRPO 使用同一 prompt 的 6 条轨迹计算 group-relative advantage。

### 2.4 Visual Experience Extraction

选择同一 prompt 下奖励最高和最低的轨迹。只有奖励差 `|Delta R| >= 0.20` 时才保留，并抽取五类经验：

- search strategy；
- knowledge activation；
- reference selection；
- prompt construction；
- failure avoidance。

经验由 Gemini 3.1 Pro Preview 总结，按源 prompt 存入 buffer。Prompt embedding 使用 Qwen3-Embedding-0.6B；buffer 容量为 500，检索余弦相似度门槛为 0.84。

### 2.5 Teacher-only SDL

- Student：只看到普通推理上下文。
- Teacher：看到普通上下文加检索到的视觉经验。
- Teacher 不生成另一条轨迹，而是在相同 student-sampled tokens 上重新计算概率。
- 使用 importance-weighted sampled-token reverse-KL。
- `lambda_SDL=2.0`，importance ratio cap 为 2.0。
- 只蒸馏关键特殊 token，并保留 teacher/student log-prob 差异最大的 top 10%。

最终目标：

```text
L_GenEvolve = L_GRPO + 2.0 * L_SDL
```

## 3. 论文数据规模

- Prompt pool：19,990。
- Knowledge-Anchored：11,999。
- Quality-Anchored：7,991。
- 结构有效 teacher trajectories：19,320。
- VLM 过滤后轨迹：13,379（69.2%）。
- SFT：8,800 train + 200 held-out。
- GT image：4,321/4,379 成功，过滤后保留 3,175。
- Self-evolution：2,575，其中 2,446 optimization、129 internal validation。
- Held-out benchmark：约 600。

## 4. 官方训练配置

### SFT

- 16 GPUs，micro batch 2，gradient accumulation 1，global batch 32。
- 2 epochs。
- AdamW，learning rate `1e-5`，weight decay `1e-6`。
- cosine schedule，warmup ratio 0.02。

### GRPO + SDL

- 1 node × 8 GPUs，rLLM/verl，FSDP actor，SGLang rollout。
- 每步 8 prompts，每个 prompt 6 rollouts。
- temperature 0.7，top-p 0.95。
- max prompt 6,144 tokens，max response 30,000 tokens。
- 每条轨迹最多 11 次 LLM 调用。
- actor learning rate `1e-6`。
- clip low/high：0.20/0.28。
- KL coefficient：`1e-3`。

完整机器可读配置见 `experiments/genevolve/paper_v2_config.json`。

## 5. 当前仓库与论文的差距

| 论文模块 | 当前状态 | 复现动作 |
|---|---|---|
| Qwen3-VL agent policy | 未实现 | 新建可训练 agent 与 ReAct rollout runtime |
| search/image_search/query_knowledge | 未实现统一协议 | 实现工具 schema、缓存和轨迹日志 |
| prompt-reference program | 部分相似 | 改为论文 JSON schema 和序数参考绑定 |
| 8 类 generation skills | 未实现 | 建立静态 skill 文本库 |
| SFT trajectory tuning | 未实现 | 接入 LLaMA-Factory 数据导出与训练配置 |
| 双奖励 KScore/text judge | 当前 Judge 不同 | 新建论文四维评分和 program sufficiency judge |
| GRPO | 未实现 | 接入 verl/rLLM 或兼容训练器 |
| 五槽视觉经验 | 当前仅保存 critique outcome | 实现 best-worst experience summarizer |
| prompt-keyed memory | 未实现 | Qwen3-Embedding 检索、500 容量、0.84 门槛 |
| teacher-only SDL | 未实现 | 修改 actor loss，增加双上下文同 token 重评分 |
| GenEvolve-Bench/WISE | 未接入 | 获取公开数据与官方评分脚本 |

## 6. 建议的三档复现

### A. 推理与评测复现

等待或获取官方 checkpoint 和数据，运行同一 Agent policy + Qwen-Image-Edit，在 GenEvolve-Bench/WISE 上重算结果。该方案最适合先验证论文结论，不需要重新构造 19,990 条数据。

### B. 缩小训练复现

使用 200～500 条 SFT 轨迹、64～128 个 self-evolution prompts、每个 prompt 2～3 条 rollout，并用 LoRA/QLoRA 训练。保留完整方法结构，但不追求论文绝对分数。必须比较：SFT only、SFT+GRPO、SFT+GRPO+SDL。

### C. 完整数值复现

严格使用论文数据量、Qwen3-VL-8B、16-GPU SFT、8-GPU GRPO+SDL、Gemini 3.1 Pro judges、Qwen-Image-Edit/Nano Banana Pro 和官方评测协议。还需要大量搜索、图像生成和 judge API 预算。

## 7. 当前机器结论

当前 Windows 环境约 16 GB RAM，未检测到可用 NVIDIA GPU，因此不能在本机完成 Qwen3-VL-8B 的 SFT 或 GRPO+SDL。当前机器适合实现代码、构建小型数据、运行 API 驱动的轨迹采集和离线评测；训练阶段应迁移到 Linux GPU 服务器。

## 8. 复现验收顺序

1. 先跑通工具轨迹和最终 JSON schema。
2. 用固定案例验证搜索、参考选择和 skill routing。
3. 完成 SFT 数据转换并训练 cold-start checkpoint。
4. 实现 KScore 与 program-sufficiency 双奖励。
5. 先跑 SFT+GRPO，确认 reward 上升。
6. 实现 best-worst experience buffer。
7. 加入 teacher-only SDL，并验证 SDL loss 下降。
8. 跑三项消融，目标复现论文趋势：`SFT < SFT+GRPO < Full GenEvolve`。
9. 最后才进行 GenEvolve-Bench 与 WISE 数值对齐。
