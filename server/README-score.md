# PDF 乐谱转调

网页默认 A 调单簧管 → 降 B 调单簧管（记谱降低一个半音，实际音高不变）。所有请求统一保留原谱分页、分行和编号，不提供版式切换。

## 当前范围

`score_skill` 为已经安装到 Codex 的 `score-pdf-transpose` 技能快照。三个适配器只接受经过校对的原 PDF 文件及 A→B♭ 请求：Nabucco 单簧管 1、2 和《万泉河水》单簧管。服务每次重新生成 PDF、逐音验证，并将生成文件摘要与已逐页检查的版本比较。原文件摘要、1850 个音符的计数及结果摘要见 `score_skill_bridge.py`。

其他文件或音程使用 Audiveris/MuseScore。该识谱路径不等于对原 PDF 的逐符号校对，尤其不能保证扫描谱、复杂声部及全音符均无遗漏；严格保版的检查不能确认原谱分行时，会返回“需复核”，不开放结果下载。2026-09-02 的独立四小节测试发现旧识谱器漏读最后一个全音符，严格保版请求被拦截。不要把此路径宣传为任意 PDF 的无损转调，不要去掉检查以制造成功。

后续优先完善通用识别与验证，不为测试集添加按谱名、文件摘要或固定坐标匹配的适配器。三个历史参考适配器只用于保留已有经过人工校对的行为。

## 通用流程改进（2026-09-02）

- `score_pdf_preflight.py` 检查嵌入 TrueType 字体。仅在字形索引、尾部零填充、符号 cmap 和 PDF 字宽共同支持时修复；不改动页面绘图指令，不覆盖上传原件。
- `score_pdf_layout.py` 从 PDF 路径提取五线谱与小节线，支持逐小节分段绘制、变换矩阵和 Form XObject；直接读取印刷数字，为 OMR 提供独立对照。不认识的绘制方式不会冒充已验证。
- 嵌入音乐字体能匹配识谱器模板时自动选择。未知字体先用 Bravura，发现结构或导出疑点时最多再用 Leland 识别一次；按漏小节、导出错误等证据选择，不能仅凭音符更多认定更好。保持串行队列，按页数分配 210–1200 秒的单次识谱超时。
- `score_transposition.py` 以调号和音程计算音名，处理跨八度的 B♯/C♭、重升降、换调、跨小节延音与和弦根音。非定音打击乐不移调。乐器模式更新 MusicXML 移调乐器信息；自定义半音模式保留原乐器信息。范围为 ±48 半音。
- `score_render_audit.py` 从最终排版文件回导 MusicXML，再核对音高、时值、休止、延音、奏法、力度、文字、反复和渐强渐弱。实际分页/系统数从渲染器导出的 print 信息读取，不再把 staff 数当 system 数。

这些检查不等于逐符号验证扫描原稿，也不保证原 PDF 中的字体、各标记坐标与 OMR 重建版完全一致。复杂声部、错误调号取消符、未识别的多小节休止仍可能需要人工复核。

测试集只用于验证。`E:\北京喜讯到边寨` 的 19 份、62 页通过字体预检，不能把这个数字当作 62 页全部音符识别正确。独立 Leland 四小节谱原先漏读最后全音符（7 音/3 小节），按字体选模板后识别为完整的 8 音/4 小节，并通过 +2 半音转调及排版回读检查。自动测试覆盖 15 种调号、53 个音程、144 种乐器组合和字体/矢量路径等边界情况。

## 运行

主 API 保持 Python 3.6 兼容，技能单独运行在 Python 3.11 以上：

```sh
python3.11 -m venv /opt/score-tools/score-venv
/opt/score-tools/score-venv/bin/pip install -r requirements-score.txt
```

可用 `SCORE_SKILL_PYTHON` 指定技能 Python 路径，默认 `/opt/score-tools/score-venv/bin/python`。`SCORE_WORK_DIR` 是任务目录，服务用户必须能写入；主服务继续使用现有 `vendor` 及 Audiveris/MuseScore 环境。

## 接口

1. `POST /api/score/transpositions`，JSON 使用 `"async": true` 和 `transposeMode: "instrument" | "custom"`。乐器模式由服务器计算音程；自定义模式必须传整数 `semitones`。旧客户端省略模式时按是否传 semitones 兼容推断。返回 HTTP 202 和 `data.jobId`。
2. `GET /api/score/transpositions/{jobId}` 获取真实阶段、进度及终态。状态为 queued、processing、completed、needs_review 或 failed。
3. 仅 `outputAllowed: true` 时开放 `outputUrl`。下载时再次比对文件摘要与检查报告，支持中文文件名和浏览器内预览。

队列串行处理，最多同时接收 5 个任务；单文件不超过 25 MB、20 页。沿用每 IP 五分钟两次的频率限制。旧前端没有 async 参数时最多等待 210 秒。页面刷新后从 sessionStorage 恢复轮询；服务重启中断的任务提示重新提交。数据不发送给外部 AI 服务。

## 验证

```sh
python -m pytest tests -q
npm run build
```

测试依赖 pytest、pypdf、fonttools，参考输入在 `tests/fixtures/reviewed_pdfs/`。设置技能 Python 为当前测试解释器后，三份真实 PDF 的运行结果必须与已检查版本完全一致。网站发布时保留原静态资源以兼容缓存页面，备份 API 与 index.html，再替换 API 并重启，健康检查通过后替换静态入口。
