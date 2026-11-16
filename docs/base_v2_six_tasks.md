# 六类基础 Prompt：标注标准更新版

版本：base_v2_six_tasks。状态：已接入批量程序，通过本地检查，未调用模型、未运行 454 张开发集推理。

这次只对齐新版《VLM可靠性-北京人工标注标准》，不是后续 RQ2 的 Prompt 优化组。

## 修改内容

- 任务由七类变为六类，删除 `bus_stop`。
- `bicycle_lane` 改为 `non_motorised_vehicle_lane`，采用新版非机动车道的定义和判断规则。
- 其余五个任务名称不变；每项仍只输出 `label`、`confidence`、`evidence`。
- 指令前缀明确本次六类。PDF 中残留的“三个任务”原文保留，由前缀说明它是旧措辞。
- 完整 Prompt 采用与 V1 相同的 PDF 文本提取及拼接方法，未额外改写判断策略。

## 六个任务键

| 中文 | JSON 键 |
|---|---|
| 路面交通标线 | road_surface_marking |
| 交通信号灯 | traffic_signal |
| 路灯 | streetlight |
| 人行道 | sidewalk |
| 交通标志牌 | traffic_sign |
| 非机动车道 | non_motorised_vehicle_lane |

`label` 仍为字符串 `"1"`、`"0"` 或 `"NA"`；`confidence` 为 0–100 整数；`evidence` 为非空的一句依据。新增 JSON Schema 文件供本地校验使用，不改变 API 请求格式。

## 保持不变的设置

模型 `qwen3.8-flash`；temperature=0；enable_thinking=false；max_tokens=1800；response_format 为 json_object。原图输入，不裁剪、不调对比度，计划每张一次调用，同时输出六类结果。

## 文件

- 指令前缀：`prompts/base_v2_six_tasks_prefix.txt`
- 模型输出规范：`schemas/base_v2_six_tasks.schema.json`
- API 配置：`configs/base_v2_six_tasks.json`（与 V1 配置逐字一致）
- 本地完整 Prompt：`data/private/base_v2_six_tasks/prompt.txt`
- 本地版本清单：`data/private/base_v2_six_tasks/manifest.json`

重新生成完整 Prompt：在安装了 pypdf 的 Python 环境中运行 `python3 scripts/build_prompt_v2.py`。输入的新 PDF 保存在同目录的 `codebook.pdf`，生成过程不联网。

`run_batch.py` 已接入六类 V2，默认只做本地检查，不读取 API 密钥，也不发送请求。它会核对完整 Prompt、PDF、schema 与准备版本的哈希，按六类解析输出。使用方法见[批量检查与运行](batch_workflow.md)。

`run_pilot.py` 仍保留历史七类 V1 的入口。新批量程序也可以通过 `--version pilot_v1` 检查历史版本。七类模型输出不能直接通过六类 schema，也不能通过改列名当作新版推理结果。程序会拒绝跨版本复用或覆盖旧运行目录。

完整 Prompt、PDF、人工标签仍留在忽略目录中；本次没有上传这些资料，也没有修改已跑的 114 张结果。
