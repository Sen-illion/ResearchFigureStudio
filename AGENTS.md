# AGENTS.md

## 协作身份

- 用户叫 Sen-illion。
- 助手叫 Kira1。
- 本文件用于帮助后续进入 `D:\ResearchFigureStudio` 的代理快速理解项目、遵守约定并安全修改代码。

## 项目一句话

ResearchFigureStudio 是一个 **PPTX-first 的科研框架图生成流水线**。它读取论文和用户提供的参考图，把参考图拆成许多局部图像槽，生成 25-50 个非箭头图像资产，再用可编辑的 PowerPoint 图层组合成科研框架图。

项目重点不是生成一张扁平化大图，而是生成：

- 可编辑的 `editable_composition.pptx`
- 槽级别 raster 图像资产
- PPT 可编辑的标签、箭头、连接线、面板、公式和分组
- 可验证的中间 JSON/Markdown 合同文件

## 当前能力边界

- 当前是早期工程原型，强项是把多个小图像块稳定放入 PPTX 精确位置。
- 生成的图像块仍然是 raster asset，不是完全可编辑的科学矢量对象。
- 不应把它宣传成端到端顶会级成图器；它更像一个方便人工继续修订的可编辑科研图生成管线。
- 项目目前最重要的开放难题是箭头和连接器定位，包括 source-target 绑定、多段路由、避让、虚线环和参考图逻辑保持。

## 技术栈

- Python 包名：`research-figure-studio`
- Python 要求：`>=3.10`
- CLI 入口：`rfs = rfs.cli:main`
- 主要依赖：
  - `pillow`
  - `python-pptx`
  - `PyMuPDF`
  - `requests`
  - Windows 上可选/条件依赖 `pywin32`
- Windows + 本机 PowerPoint 是最佳导出环境，因为 PDF/PNG 导出依赖 PowerPoint COM 和 PyMuPDF。

## 目录结构

- `rfs/`：主 Python 包。
- `rfs/cli.py`：命令行入口，提供 `doctor`、`make-framework`、`validate`。
- `rfs/workflow.py`：主流水线编排。
- `rfs/validator.py`：输出合同验证器，是交付前的硬门槛。
- `rfs/input_archive.py`：归档输入论文和参考图。
- `rfs/input_loader.py`：抽取文档文本。
- `rfs/paper_analyzer.py`：生成论文 grounded brief。
- `rfs/reference_analyzer.py`：从参考图和论文目标生成 slot inventory、geometry、controls、色彩 token。
- `rfs/stylist.py`：生成 reference style profile 和 style sheet。
- `rfs/layout_locator.py`：生成 `layout_plan.json`；heuristic 本地可跑，VLM 只应返回坐标 JSON。
- `rfs/program_builder.py`：生成 `figure_program.json`，这是 PPT 编译的单一布局源。
- `rfs/prompt_planner.py`：生成 `slot_visual_spec.json`、`reference_slot_prompt_brief.json`、`slot_prompt_plan.json`，默认 VLM 按槽规划 prompt。
- `rfs/asset_generator.py`：生成多候选图像资产，支持 `placeholder`、`gemini`、`image2`，并写出质量/复杂度报告与 contact sheet。
- `rfs/asset_reviewer.py`：对已选图像资产做 heuristic 或 VLM 审查。
- `rfs/ppt_compiler.py`：把 `figure_program.json` 编译为可编辑 PPTX。
- `rfs/exporter.py`：导出 `review.pdf` 和 `final_600dpi.png`，本机不支持时会降级为 PPTX only。
- `rfs/visual_critic.py`：比较参考图与最终渲染，VLM 模式可提出布局修正。
- `codex-skills/research-figure-making/`：随仓库提供的 Codex skill，描述完整科研制图工作流。
- `codex-skills/research-figure-making/scripts/validate_framework_outputs.py`：独立输出验证脚本。
- `tests/`：当前主要覆盖验证器。
- `docs/architecture.md`、`docs/workflow.md`：架构和流程说明。

## 核心工作流顺序

严格顺序如下：

```text
input archive -> paper brief -> reference_geometry.json/reference_controls.json ->
reference_style_profile.json/style_sheet.md -> layout_plan.json ->
figure_program.json -> slot_visual_spec.json -> reference_slot_prompt_brief.json ->
slot_prompt_plan.json -> multi-candidate slot assets ->
asset_quality_report.json/asset_complexity_report.json/asset_visual_review.json/contact sheets ->
editable_composition.pptx -> PDF/PNG export -> visual_critic_iter_0.json ->
alignment_review.md/critic_report.md -> validation
```

重要原则：

- 参考图在 `--slot-source reference-primary` 下是布局、局部视觉对象、颜色、视觉节奏和箭头逻辑的最高权威。
- 论文负责科学术语、模块含义和概念映射，不应把参考图覆盖成通用模板。
- 箭头、连接线、虚线环、面板框、标签、公式和关键文本必须是 PPT 可编辑对象，不应作为图像资产生成。
- 普通非 legend 槽应是 dense mini scientific scene/card，包含 2-5 个层次对象和微细节，不应只是居中小图标。
- 禁止生成一张完整架构大图后裁剪或截图作为交付。
- 禁止 semantic crop、cover-crop、crop-to-ratio；图像插入应是 contain/no-crop 语义。

## CLI 常用命令

安装开发包：

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

健康检查：

```powershell
rfs doctor --json
```

离线烟测，使用 placeholder，不调用外部 API：

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out "output\offline_check" `
  --asset-mode placeholder `
  --locator-mode heuristic `
  --prompt-plan-mode heuristic `
  --slot-count 36 `
  --candidates-per-slot 3 `
  --asset-review-mode heuristic `
  --critic-mode heuristic `
  --json

rfs validate --out "output\offline_check" --json
```

真实 VLM + 图像生成推荐从小规模开始：

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out "output\real_small" `
  --slot-count 25 `
  --slot-source reference-primary `
  --complexity-profile reference-dense `
  --candidates-per-slot 1 `
  --locator-mode vlm `
  --prompt-plan-mode vlm `
  --prompt-plan-workers 4 `
  --asset-mode image2 `
  --asset-workers 3 `
  --asset-retries 2 `
  --asset-review-mode heuristic `
  --critic-mode heuristic `
  --json
```

## 环境变量与密钥

不要把 API key 写入源码、文档示例的真实值、测试夹具或输出目录。只使用环境变量：

- `API_BASE`
- `API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_GEN_IMG_URL`
- `MODEL_VLM`
- `RFS_LOCATOR_MODEL`
- `RFS_PROMPT_PLANNER_MODEL`
- `RFS_CRITIC_MODEL`
- `RFS_IMAGE_MODEL`
- `IMAGE_MODEL`

`image2` 的逻辑模型名默认映射为 Yunwu 暴露的 `gpt-image-2`，除非 `RFS_IMAGE_MODEL` 或 `IMAGE_MODEL` 覆盖。

## 输出合同

一个有效的 image-rich framework run 通常必须包含：

- `input_manifest.json`
- `paper_brief.md` / `paper_brief.json`
- `reference_geometry.json`
- `reference_controls.json`
- `slot_inventory.json`
- `reference_style_profile.json`
- `style_sheet.md`
- `layout_plan.json`
- `figure_program.json`
- `slot_visual_spec.json`
- `reference_slot_prompt_brief.json`
- `slot_prompt_plan.json`
- `prompts.md`
- `reference_slot_crops/<slot_id>.png`
- `assets/*.png`，普通系统图至少 25 个非箭头图像资产
- `asset_candidates/*/candidate_*.png`
- `asset_quality_report.json`
- `asset_complexity_report.json`
- `composition_quality_report.json`
- `asset_visual_review.json`
- `asset_contact_sheet.png`
- `asset_candidate_contact_sheet.png`
- `editable_composition.pptx`
- `review.pdf` 和 `final_600dpi.png`，本机导出可用时生成
- `visual_critic_iter_0.json`
- `alignment_review.md`
- `critic_report.md`

文本 artifact 的开头约定：

- Markdown 的第一个非空标题应为 `# Summary` 或 `## Summary`。
- JSON 应包含顶层非空 `summary` 字段。

## 验证规则重点

`rfs.validator.validate_output` 和 skill 脚本会阻塞以下情况：

- 缺少必需 artifact 或 artifact 为空。
- 少于 25 个 selected 非箭头图像资产。
- `figure_program.json` 不含 PPTX export target。
- 箭头、transition、dashed loop、connector 出现在 `slots` 或 `assets` 中，而不是作为 PPT control/arrow。
- 槽位使用粗略比例，如 `1:1`、`4:3`、`3:4`、`16:9`、`9:16`，而不是 `1.000:1.000` 这类精确小数比。
- 图像槽缺少 `reference_crop_path`、`reference_style_profile_path` 或 `local_color_token_ids`。
- 非 legend 槽缺少至少 2 个 `secondary_objects` 或至少 2 个 `micro_details`。
- 图像内容填充低于最小值，或空白边距超过最大值。
- 插入 PPT 后额外添加白色 tile/frame、caption 在图像槽内，或图像槽填充低于 95%。
- 发现 forbidden markers，如 `single full diagram`、`vector-only`、`svg-only`、`cover-crop`、`baked labels` 等。
- `asset_visual_review.json` 或 `visual_critic_iter_0.json` 报告未解决阻塞问题。

## 开发与测试

本地开发检查：

```powershell
python -m compileall -q rfs
python -m py_compile codex-skills\research-figure-making\scripts\validate_framework_outputs.py
python -m py_compile codex-skills\research-figure-making\scripts\estimate_asset_fill.py
python -m unittest discover -s tests -q
```

CI 在 Windows 上跑 Python 3.10 和 3.11，步骤包括：

- editable install
- compile `rfs`
- py_compile skill scripts
- unittest
- 检查 bundled skill frontmatter

## 仓库卫生

不要提交：

- `output/`、`outputs/`
- 论文、手稿、私有数据、用户参考图
- 生成的 PPTX/PDF/PNG/JPG/SVG/TIFF/WebP 等图像或成图资产
- `.env`、API key、私钥
- `__pycache__/`、`.pytest_cache/`、`*.egg-info/`
- 本地虚拟环境，如 `.venv/`

当前 `.gitignore` 已经覆盖多数生成物。注意 `AGENTS.md` 当前是工作区新增文件，修改时不要误删用户内容。

## 修改代码时的建议

- 优先保持现有 deterministic pipeline 结构，不要把坐标、prompt、资产生成和 PPT 编译混成一个大脚本。
- 对 JSON/Markdown 输出继续使用 `rfs.utils.write_json` 和 `write_text`，保持 UTF-8 和 `ensure_ascii=False`。
- 新增 artifact 时同步考虑 validator、docs、README 和 tests。
- 修改输出合同相关代码后，优先补充 `tests/test_validator.py`。
- VLM 只能产生结构化 JSON、布局建议或 prompt 计划；不要让 VLM 直接写任意 PowerPoint 代码。
- 真实 API 失败时不要静默切换到 placeholder 或 vector-only；应明确失败或让调用者选择 fallback。
- 保持 labels、formulas、arrows、controls 在 PPT 层可编辑，图像资产只承载局部视觉块。
