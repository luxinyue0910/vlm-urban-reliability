# 城市街景 VLM 可靠性研究

研究目标：在不重新训练 VLM 的情况下，比较图像处理和提示词能否减少错误，再用风险信号挑出值得人工复核的图片。

**当前阶段：10 张全景图的流程试跑。正式基线和六组实验尚未完成。** 已获得七类设施共 70 项模型输出。当前人工试标不作为正式真值，此次不公开人工标签、人机对比或逐项复核结果，也不报告模型准确率。

## 四个研究问题

| RQ | 主要问题 | 当前进展 |
|---|---|---|
| RQ1 | 模型错在哪里，哪些图片条件更容易出错？ | 已收集模型输出，尚未做正式关联分析 |
| RQ2 | Prompt、裁剪、对比度、按条件处理是否有效？ | 原图试跑完成；六组对照待实现 |
| RQ3 | Confidence、图片质量、两者结合能否筛出错误？ | 保存了 confidence，质量评分与校准待实现 |
| RQ4 | 相同人工预算下，风险优先是否优于随机复核？ | 模拟与实际计时待实现 |

## 仓库内容

- `scripts/`：生成 Prompt、顺序调用 API、准备本地标注网页、重算试跑一致率。
- `web/`：10 张图的人工标注界面；先标注、锁定，再显示模型结果。当前浏览器自动保存，换设备需导出备份。
- `prompts/`、`configs/`：试跑指令前缀和实际调用设置。
- `results/pilot10/`：去除原始文件名后的模型预测和运行记录，不包含人工标签或基于人工标签的分析。
- `docs/`：研究方案、16 篇工作版文献矩阵、输出记录说明。
- `data/pilot_manifest.json`：10 张图的匿名编号、选择原因和哈希；原图与队友的 PDF 未公开。

本仓库没有 API 密钥、街景图片、队友提供的 PDF 或私人站点部署凭据。公开 Prompt 只包含指令前缀；完整 Prompt 需在本地加入原 PDF。未获得这些资料的读者可以检查公开结果与计算，但不能完整重现图像推理。

## 已完成试跑

实际运行请求及返回模型均为 `qwen3.8-flash`，temperature 为 0，关闭 thinking，每图一次成功请求，使用原始全图，无裁剪或对比度处理。模型名称与设置来自本次归档记录，不表示已完成候选模型比较或保证未来仍可调用。

七类设施：路面交通标线、交通信号灯、路灯、人行道、交通标志牌、公交站、自行车道。每项输出 `label`（`1` / `0` / `NA`）、`confidence`（0–100 整数）、一句 `evidence`。Confidence 是模型对所选标签的自报把握，不是校准后的正确概率。

```bash
python3 scripts/compare.py --human data/private/your_annotations.json
```

这个命令需要你自行提供网页导出的人工标注文件，计算当前标签与模型的一致情况，不调用 API。仓库不附人工标注文件；输出仅用于本地检查。详见 [模型试跑记录与限制](docs/pilot_findings.md)。

## 本地运行

以下命令均从仓库根目录运行。Python 3.10 或更高版本；仅生成完整 Prompt 时需要 pypdf。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

将有权使用的 10 张原图放到 `data/private/images/P01.jpg` 至 `P10.jpg`，PDF 放到 `data/private/codebook.pdf`。这些目录不会提交 Git。不要把任意新图覆盖为已有 P 编号：当前清单会验证图片哈希。

```bash
python3 scripts/build_prompt.py
python3 scripts/run_pilot.py --dry-run
```

Dry run 检查图片、Prompt 和配置，不联网、不收费。实际调用前，在终端环境中设置 `DASHSCOPE_API_KEY`（脚本不自动读取 `.env`），再运行：

```bash
python3 scripts/run_pilot.py --output runs/new-pilot
```

这会向配置中的 API 发送图片和完整 Prompt，并产生 API 费用。每图至多一次请求，不自动重试、不覆盖已有运行目录；失败记录保留。新脚本是原试跑脚本的可移植整理版，尚未用 API 重新验证；历史结果来自此前原始脚本。

### 打开本地标注网页

```bash
python3 scripts/prepare_web.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory web
```

打开 `http://127.0.0.1:8000`。图片与标注标准来自本地文件；网页不会调用 VLM。模型结果仅在界面锁定并点击比较后显示，但静态文件并无访问控制，不能作为严格盲法研究平台。备份包含个人标注，不要提交到公开仓库。此版本保留原试跑数据集标识以兼容已有备份；新数据批次需更换标识及清单。

## 文档版本

以 [当前研究方案](docs/research_plan.md) 为当前范围说明。`protocol_v6.2_historical.pdf` 是七类设施试跑之前的三页计划，保留了“三个任务/模型待定”等历史措辞，不能直接作为当前执行配置。文献矩阵和输出 schema 均为工作材料，此次整理没有重新核验全部文献。正式样本量、划分、标注边界和验证模型还需确定。

数据来自团队资料，未在此仓库授予再分发权限。研究仍在开发阶段，没有宣称完成 RQ1–RQ4 或证明节省人工。
