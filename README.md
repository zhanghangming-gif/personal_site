# hangminglab.cloud 个人网站

这是 [hangminglab.cloud](https://hangminglab.cloud) 的完整网站源码，包含 React 前端、Python API、留言与管理后台，以及 PDF 乐谱识别、转调、复核和人工校谱流程。

## 目录

- `src/`：React、TypeScript 和 Tailwind CSS 前端。
- `public/`：网站照片、视频、证书、简历等静态资源。
- `server/`：Python API、乐谱 OMR/转调管线、在线校谱和部署配置。
- `server/score_skill/`：乐谱转调 Skill 及其辅助脚本和参考资料。
- `tests/`：后端与乐谱处理回归测试。

仓库不包含生产密码、API Key、TLS 私钥、留言数据库、访客上传文件、乐谱任务工作区或服务器备份。

## 前端开发

要求 Node.js 18 或更高版本：

```bash
npm install
npm run dev
```

生产构建和代码检查：

```bash
npm run lint
npm run build
```

构建产物位于 `dist/`，部署时把其中内容同步到 Nginx 站点目录。

## 后端开发

网站 API 入口为 `server/message_api.py`。基础依赖和乐谱代理依赖分别位于：

```bash
python -m pip install -r server/requirements-score.txt
python -m pip install -r server/requirements-score-agent.txt
```

复制环境变量模板并填入本机值：

```bash
cp server/.env.example server/.env
```

不要把真实 `.env`、密码哈希或 API Key 提交到仓库。

## 乐谱转调流程

当前通用流程包括：

1. PDF 预检和多分辨率渲染。
2. Audiveris OMR 与 MusicXML 结构修复。
3. 确定性音高转调。
4. MuseScore 生成候选 PDF。
5. 音符、节奏、休止符、小节数和排版复核。
6. 高置信休止符候选经用户查看原谱局部并确认后，生成新的 MusicXML 和 PDF 版本。

架构细节见 `server/SCORE_COMPILER_ARCHITECTURE.md`，编辑约束见 `server/README-score-editor.md`。

## 测试

```bash
python -m pytest -q
```

前端同时运行：

```bash
npm run lint
npm run build
```

## Linux 部署

- Nginx 示例：`server/nginx.personal-site.conf`
- Nginx 限流：`server/nginx-rate-limits.conf`
- systemd 服务：`server/personal-site-message-api.service`
- 生产环境变量模板：`server/.env.example`

生产机需单独安装并配置 Audiveris、MuseScore、Poppler/PyMuPDF 以及相关字体。TLS 证书和生产环境变量由服务器管理，不属于源码仓库。
