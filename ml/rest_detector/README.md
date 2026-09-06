# Rest Detector

这个目录用于训练“休止符局部视觉检测器”。模型只观察已经定位的谱表/小节裁片，不负责整页 OMR，也不单独决定是否修改 MusicXML。

## 训练位置

训练在本地 RTX 4050 Laptop 6 GB 上进行。生产服务器没有 GPU，只对 Rhythm Gap Detector 提出的少量局部区域运行推理。

## 标签

`classes.json` 包含当前休止符类别。多小节休止横线单独作为 `multi_measure_rest`，横线上方数字继续由数字 OCR 读取。附点存为标注属性，不单独作为目标类别。

每个目标至少需要：

- 精确边界框；
- 休止符类别；
- 附点数；
- 所属谱表；
- 是否经过人工确认。

OMR 候选只能作为预标，不能直接成为训练真值。

## 1. 导出待标注样本

```powershell
python ml/rest_detector/export_review_queue.py `
  --jobs-root D:\score-jobs `
  --output ml/rest_detector/data/review-v1 `
  --dpi 800
```

脚本读取每个任务的：

- `input.pdf`
- `review/rhythm-gaps.json`
- `review/rest-classification.json`

并生成：

- `images/*.png`：缺口所在的小节局部；
- `queue.jsonl`：人工标注队列；
- `manifest.json`：数据版本与统计。

重新执行时会保留已经人工修改过的 `annotation` 和 `state` 字段。

## 2. 数据拆分

必须按 `documentSha256` 拆分 train/validation/test。同一份 PDF 的不同小节不能同时出现在训练集和测试集，否则指标会虚高。

初版目标：

- 20,000 个合成小节；
- 2,000–5,000 个真实人工确认小节；
- 20%–30% 不含休止符的困难负样本；
- 每个常用类别至少 500 个真实实例。

## 3. 训练基线

先用 TorchVision Faster R-CNN + FPN。6 GB 显存建议小节裁片宽度不超过 1280 px、batch size 1–2，并启用自动混合精度。

Windows CUDA 12.8 环境可参考 PyTorch 官方版本页面安装匹配的 `torch` 和 `torchvision`。模型代码在数据标注流程稳定后加入，避免在错误标签上训练。

## 4. 上线门槛

分别报告：

- 每类 AP/召回率；
- 全休止与二分休止混淆率；
- 节奏缺口区域召回率；
- 错误自动补入率；
- 按出版社、扫描/矢量 PDF 和清晰度分组的结果。

模型输出只是新证据。只有视觉结果、时间轴缺口和谱表几何一致，并经过用户确认时，网站才写入休止符。
