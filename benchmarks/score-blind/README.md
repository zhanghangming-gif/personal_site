# 冻结声部谱评测集

`manifest.json` 从 2026-09-09 起冻结，PDF 保存在仓库外。11 份文件都用 SHA-256
绑定，并明确 `exclude_all_cases`。训练导出接口会按文档摘要强制排除这些谱的全部裁片，
不能依靠人工记忆隔离数据。

这批谱在冻结前曾用于人工观察通用流程，因此它是“从冻结日开始的前瞻盲测集”，不能
冒充从项目第一天起完全不可见的学术盲测集。已经进入标注库的《伏尔塔瓦》未纳入清单。
以后新收集的真正未见谱应先写入新版本清单并冻结，再运行第一次基线；不能针对单份失败
修改规则后仍把它称为盲测。

只校验清单和本地文件，不运行识谱：

```powershell
python server/score_regression_runner.py `
  D:\Codex\score-training-scores `
  D:\Codex\score-benchmark-runs\validate `
  --manifest benchmarks/score-blind/manifest.json `
  --validate-only
```

运行完整基线：

```powershell
python server/score_regression_runner.py `
  D:\Codex\score-training-scores `
  D:\Codex\score-benchmark-runs\baseline-v1 `
  --manifest benchmarks/score-blind/manifest.json
```

只运行一个案例做流水线冒烟测试时，可追加：

```powershell
  --case-id farrenc-overture2-tenor-trombone
```

之后的候选版本必须与固定基线比较：

```powershell
python server/score_regression_runner.py `
  D:\Codex\score-training-scores `
  D:\Codex\score-benchmark-runs\candidate `
  --manifest benchmarks/score-blind/manifest.json `
  --baseline D:\Codex\score-benchmark-runs\baseline-v1\regression-report.json
```

报告会列出每份谱的处理状态、失败类别、识谱尝试、节奏缺口、溢出、音符数、
小节数、标题区域保留状态，以及相对基线新增的失败。只有固定期望全部通过且没有
基线退化，`evaluation.passed` 才为 `true`。
