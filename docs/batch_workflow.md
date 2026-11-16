# 六类批量程序：先检查，再运行

`scripts/run_batch.py` 默认使用六类基础版 V2，默认只做本地检查。以下检查不会调用模型，不要求 API 密钥。

先按[六类版本说明](base_v2_six_tasks.md)放入对应 PDF 并生成完整 Prompt。模型仍为 qwen3.8-flash，temperature=0，关闭 thinking，max_tokens=1800，返回 json_object；每张原图一次请求，同时返回六类字段。没有加入裁剪或对比度处理。

## 只检查

将下面的图片目录替换为本机路径，使用新的输出目录。批量入口读取目录第一层的 JPEG 原图（`.jpg` / `.jpeg`），不递归扫描子目录：

```bash
python3 scripts/run_batch.py \
  --version base_v2_six_tasks \
  --images /path/to/development-images \
  --output runs/development_v2 \
  --dry-run
```

输出 `preflight.json` 和 `images.json`，记录图片清单、版本哈希、任务数、预计输出行数和可复用数量。454 张对应 2,724 项预计判断，检查文件不是模型预测。即使省略 `--dry-run`，默认也不会调用 API。

## 检查图片重合

```bash
python3 scripts/audit_images.py \
  --development /path/to/development-images \
  --reference /path/to/reference-images \
  --output runs/development_audit/overlap_audit.json
```

检查同名文件、文件字节哈希、解码后的 RGB 像素哈希、各集合内部重复，以及跨集合的 dHash 相似候选。像素检查采用 EXIF 方向转换，只用于检查，不改写原图。dHash 以 256 位相邻灰度差生成，默认距离不超过 8 的画面对列为待人工查看候选；没有候选不保证没有近似视角、裁剪或拼接后的重复。

另按文件名中的视频编号统计共享来源，以及同一视频内最近的 site 编号差。视频相同不等于图片重复，编号差也不是实测距离或时间；独立测试集需要额外考虑来源和空间分组。检查程序不删除、移动或排除图片，不上传数据。

## 将来实际运行时

只有显式加 `--execute` 才会读取 `DASHSCOPE_API_KEY` 并发送请求，产生 API 费用。当前只授权本地检查，尚未执行开发集模型推理。

每张结果单独落盘；同一版本、输入清单和输出目录可恢复已有记录。成功项不重复调用，失败项也保留供检查，不会在恢复时偷偷重试。明确的 HTTP 429/5xx 最多尝试三次；模型格式错误和可能已计费的网络超时不自动重试。认证失败停止后续未开始的请求。

`--reuse /path/to/old-run` 仅允许模型、Prompt、PDF、推理参数、schema、图像处理和实际请求内容均匹配的结果。七类 V1 与六类 V2 不兼容，即使图片相同也不能复用。旧运行目录不会被新版覆盖，需使用新的输出目录。

记录区分本次启动的调用数 `api_calls_this_invocation` 和整次实验累计尝试数 `api_attempts_in_run`。`usage.new_run` 包含该运行中此前启动已保存的回答用量，不代表本次恢复额外产生的费用；服务器未返回的用量无法从本地记录确定。

## 本地验证

```bash
python3 -m unittest discover -s tests -v
```

测试用合成回答替代全部 HTTP 调用，覆盖六类解析、默认不联网、拒绝七类结果、恢复不重复调用、跨版本复用拒绝、以及文件与像素重复的区别。测试不是实际模型推理。

图片、完整 Prompt、标注标准和检查明细保存在 Git 忽略的本地目录；人工标注不公开。
