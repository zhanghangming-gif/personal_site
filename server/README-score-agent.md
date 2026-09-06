# 按谱生成脚本的 AI 转谱代理（实验接入）

这是 DeepSeek 驱动的代理，不是 Codex，也不共享 Codex 桌面订阅、会话或模型。
复用网站服务端的 `DEEPSEEK_API_KEY` 和官方 `DEEPSEEK_API_URL`；网站聊天模型不变。
独立设置 `SCORE_AGENT_MODEL`，默认 `deepseek-v4-pro` 负责规划和代码；
`deepseek-v4-flash-vision-exp` 通过读图工具回答具体谱面问题，账户可用性须实测。
视觉观察也可能出错，必须与图形和音乐结构证据核对，不能直接当作正确答案。

每个任务启动独立工作目录。AI 通过工具循环检查 PDF、查看谱面裁图、编写当前文件的
Python 脚本、执行脚本、读错误并修改。没有按文件哈希匹配的成品库，也不自动调用固定
Audiveris→MuseScore 流程。`score_transposition.py` 等通用工具仅作为可调用的基础工具。
保留任意整数半音移调、乐器换调含义和原谱分页/编号/全部演奏标记的要求。

## 状态与接入

此接入为实验功能。默认 `SCORE_ENGINE=omr` 保持已上线功能；在隔离环境完成验证后，
可由服务管理员设置 `SCORE_ENGINE=deepseek-agent`。客户端上传参数不能选择执行引擎。
选择代理后，错误不会退回旧流程。仅有 API Key 仍不足以部署：工作进程还需要下面的
独立资源隔离和 Python 库。

当前独立验证只确认候选 PDF 的可读性、页面几何和输入摘要。模型自己写的音符清单、
自检脚本和“全部正确”不能作为原谱正确性的独立证明。因此候选始终为 `NEEDS_REVIEW`，
不会通过旧下载接口发放。必须后续完善原谱独立验证/复核流程后才能开放自动交付。
这不等于已经实现任意谱子自动无误，也不应宣传为已完成 Codex 接入。

## 工作进程部署条件

- Linux、Python 3.11、bubblewrap、Poppler；现有 pypdf/fontTools 及
  `requirements-score-agent.txt` 中的附加库。
- 独立 systemd 工作进程/cgroup，内存上限至多 1 GiB、进程数至多 64。
  工作进程会检查实际 cgroup，缺少限制就停止。不要为方便测试删除检查。
- 生成脚本以清空的环境运行，关闭网络和其他命名空间，仅挂载当前只读输入、精选
  只读工具库、系统运行库和当前任务工作区。密钥只在外层 API 客户端中使用。
- 工作区位于 `/dev/shm`，聚合文件增长计入工作进程内存限制；单文件至多 25 MiB。
  每段代码至多 45 秒、每个任务至多 15 分钟，默认最多 16 次 API 调用（硬上限 24）。
  部署单次任务服务时使用 `TemporaryFileSystem=/dev/shm:size=512M,mode=1777`，使任务
  被强制终止后，临时文件也随服务挂载命名空间销毁，不能依赖 Python finally 清理。
- 公网启用前应让代理运行在独立工作服务中，以免资源限制作用于网站主服务。
  不要把 Codex CLI 或任意 shell 直接暴露为公网接口。

单次测试：建立一个只有 `input.pdf` 和 `request.json` 的任务目录，在独立受限进程中运行
`python score_agent_worker.py /absolute/job/path`。请求格式沿用网站 API，必须包含
`transposeMode`、`semitones`、`sourceInstrument`、`targetInstrument`、`accidentalPreference`。

候选、可复现脚本与音符审计记录保存在任务的 `agent-work/`。模型调用记录和用量留在
任务目录，禁止公开为静态文件；不记录密钥或请求头。查看 JSON 中的状态再判断是否完成。

官方接口参考：
- https://api-docs.deepseek.com/guides/tool_calls/
- https://api-docs.deepseek.com/guides/vision/
- https://learn.chatgpt.com/docs/codex-sdk

## 2026-09-05 的实际验证结果

服务器现有密钥的模型列表包括 V4 Flash、V4 Pro 和 Flash Vision Exp。
真实请求已验证看图、工具调用、Python 执行和错误反馈；没有训练模型。
运行隔离实测通过：输入只读、当前工作区可写、网站与配置不可见、密钥不在生成代码的
环境中、网络关闭。新增 12 项代理测试通过；此前完整测试集 102 项通过，最后新增了
模型分工测试并重跑代理测试。程序测试结果不代表识谱正确率。

测试输入为已有正确 MusicXML 对照的一页、四小节、八个音符的独立小谱。
视觉模型单独承担代理任务的 8 次、24 次调用试验均在上限内未提交候选。
Pro 负责代码、视觉模型负责读图的 16 次总调用试验也未提交可复核 PDF。
其中一次视觉读图把不同音高都描述为 G，并多描述了原图不存在的音符，不能作为真值。
这些有限轮次的结果不证明增加预算也无法完成，但不足以启用公网自动交付。

试验在 `/opt/personal-site-staging/score-agent-20260905` 的独立 systemd 单次任务中运行。
没有切换线上 `SCORE_ENGINE`，没有把接入代码部署到线上主服务，也没有生成可交付的
移调 PDF。下一步需要改进任务规划、图形证据提取和原谱独立验证，再进行新的受限评测。
