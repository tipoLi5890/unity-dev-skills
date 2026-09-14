# unity-dev-skills

[繁體中文](README.zh-TW.md) · **简体中文** · [日本語](README.ja.md) · [English](../README.md)

面向 AI 编码代理的 Unity 6 游戏开发 skills。三十四个 skill，覆盖从空项目到可验证产物的完整闭环，
可安装到 Claude Code 或 OpenAI Codex。

有三点让它不只是一堆 Unity 笔记：

1. **它是自足的。** 没有任何一个 skill 会让你先去装别的东西。它们通过各自的
   `Scope — what this skill does NOT do` 段落互相导流，所以无论你从哪个方向进来，都会落到对的那一个。
2. **每个 skill 都是一套在你自己的项目上执行的方法。** 要检查什么、怎么检查，以及负责做这些事的
   代码 —— `scripts/` 里的 Python、`resources/` 里的 C# 与 shader 源码、`templates/` 里整份
   复制走的文件 —— 不是要你重敲一遍的笔记。
3. **Skills 是按加载情境拆分的，不是按主题。** 一份 `SKILL.md` 是带着症状路由表的路由器，
   深度内容放在它指名的 `reference/` 文件里，所以一个 skill 只会把当下情境需要的东西加载进来。

## 安装

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

Codex 读取的是同一棵树：把它指向 `.agents/plugins/marketplace.json`，只要 plugin 本身的话就指向
`.codex-plugin/plugin.json`。两份都由 Claude 格式的 manifest 生成，所以不可能说出不一样的话。

也可以把 skills 直接放进项目 —— 把 `skills/*` 复制到 `<项目>/.claude/skills/`。

## Skills 一览

| 分组 | Skill | 什么时候加载 |
|---|---|---|
| **终端与验证** | `unity-cli` | 从终端驱动 Unity：editor、许可、template、CI、MCP，以及能告诉你"重试是否诚实"的 exit code |
| | `unity-debug` | 你需要验证一个看不见的改动 —— 并且在相信测量工具之前，先证明它说的是真话 |
| | `unity-play-harness` | 把游戏做成 agent 能驱动、能读懂的样子：一行 probe 快照、直接开进某个时刻并等待"就绪集合"的具名 situation、采样成时间线并断言不变量的 journey test，以及把一句手感抱怨变成可复现的测试 |
| | `unity-profiling` | 慢帧或不稳定的帧背后到底在做什么工作：不开 Profiler 窗口的 counter、90 帧窗口的 median/p95/worst、工作量计数，以及一张前后对照表 |
| | `unity-search` | 把"找一下／在哪里／谁引用了它"变成一条 Unity Search 查询：类型 filter、文件夹、label、`ref=` 关系、场景组件查询 —— 先把查询写给你看，Editor 还活着时顺手帮你打开窗口 |
| **第一天** | `unity-new-project` | 事后补救代价很高的决策：editor 版本锁定、`.meta`/LFS、UPM 锁 tag、IL2CPP/ARM64、asmdef 边界 |
| | `unity-game-brief` | 动 Unity 之前的第一个小时：一行想法变成一页体验简报、用图锁定视觉、由约束推导出架构提案、写成可测试的不变量，以及一个人能真的玩到的交互 |
| **UI** | `unity-game-ui` | **任何 UI 需求都从这里开始。** 检测项目使用的是哪套 UI 系统并导流；并且承担没人写的那一块 —— runtime `OnGUI` HUD |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— 以及 uGUI 什么都画不出来的六种原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— 以及 USS 会静默忽略的那些属性 |
| **资源** | `unity-3d-models` | 静态道具：在 Unity 看到它们之前，先导入并减面 AI 生成的网格 |
| | `unity-2d-sprites` | Sprite sheet、切图、pivot、9-slice、把一组逐帧做成可播放的 `AnimationClip` —— 那些住在 importer 里的元数据 |
| | `unity-2d-pixel-perfect` | 像素画发虚、镜头一动像素就爬、tile 之间出现发丝缝 —— 以及你手上到底是哪一个叫 `PixelPerfectCamera` 的组件 |
| | `unity-sprite-atlas` | 该共用一次 draw call 的 sprite：用脚本产 V2 atlas、打包与平台设置，以及打包好的贴图怎么到玩家手上 |
| | `unity-tilemap` | 矩形、六角与等角网格的 Tile Palette，以及用手上现成的地形图产出 RuleTile |
| | `unity-rigged-character` | 可操作的角色：原画 → image-to-3D → Mixamo → Avatar → Animator → gameplay rig |
| **AI 素材生成** | `codex-visual` | 用 `codex` 图像模型出 2D 美术，靠一份美术圣经与一张锚定图锁住风格：grid one-shot 整组、短动画生成成一张 sprite sheet 再切成量测过的逐帧并输出 GIF 预览、去背、尺寸归一化 |
| | `comfyui-asset-generation` | 用自建 ComfyUI 出音乐、音效与 MiniMax H3 视频：一次一件、只信 `/history`、切模型前先 `/free` |
| **运行时领域** | `unity-physics-3d` | 永远不触发的碰撞或 trigger、高速穿透、明明就在正前方却打不到的 raycast |
| | `unity-navigation` | NavMesh、agent、障碍物、link —— 以及决定谁拥有 transform |
| | `unity-render-urp` | 设了却不出现的后处理、移动端负担得起的子集、Render Graph 审查 |
| | `unity-urp-migration` | 把 Built-in 项目分五个带闸的阶段搬到 URP，每一阶段都从存盘后的项目读回来验证；也用来诊断搬到一半的项目：整片洋红、PPv2 转成 Volume、从来没重烤的 lightmap、`GrabPass`／`OnRenderImage` |
| | `unity-audio` | 内存、load type、采样率、mixer 开销 —— 它会先报告再重新导入 |
| | `unity-localization` | 用一种以上的语言发布，以及真正会出问题的 CJK 字体管线 |
| **发布** | `unity-android-release` | 构建完之后**证明**它：把产物读回来、keystore 与 versionCode 纪律 |
| | `unity-web-release` | WebGL/WebGPU 的下载体积、服务器响应头、浏览器内存上限 |
| **后端与商业化** | `unity-live-services` | 这个 build 在跟哪个环境通信、密钥该放哪、先设计离线路径 |
| | `unity-ugs` | Gaming Services 的 API 表面：哪个包提供什么、其他一切都依赖的初始化顺序、Cloud Save 的访问类别、Cloud Code、Remote Config |
| | `unity-iap` | 逐个调用写 In-App Purchasing v5：连上商店、pending/confirm 流程、收据、权益、restore —— 以及内容发了两次或一次都没发 |
| | `unity-ads-levelplay` | LevelPlay 广告聚合：原生依赖解析、init 之前的同意流程、rewarded/interstitial/banner 广告单元、单次曝光级别的收入 |
| | `unity-monetization` | IAP 与广告 SDK 撞上发布流程的地方：merged manifest、商店声明、收据 |
| | `unity-multiplayer` | 拓扑是那个代价很高的决定，加上语音聊天与麦克风争用 |
| | `unity-multiplayer-services` | Sessions：玩家怎么进到同一局游戏 —— join code、可浏览的房间列表、quick join、ticket 匹配、relay、host 迁移、专用服务器 |
| | `unity-vivox` | 逐个调用接语音与文字聊天：登录、group/echo/定位频道、参与者名单、mute 与 push-to-talk、麦克风权限 |

## 在这个 repo 上工作

```bash
python3 tools/lint-skills.py            # frontmatter + name 与目录名一致 + 大小上限 + 可执行文件语法
python3 tools/check-consistency.py      # manifest 一致、外部依赖已声明
python3 tools/sync-codex-manifests.py   # 重新生成 Codex manifest
claude plugin validate .                # manifest 形状
```

`.claude-plugin/*` 是事实来源。`.codex-plugin/plugin.json` 与 `.agents/plugins/marketplace.json`
是**生成物 —— 永远不要手动编辑它们。**

路由到本 repo 以外的 plugin 算一项**声明过的依赖**：把它加进 `tools/check-consistency.py` 的
`COMPANIONS`，并写上理由。没声明的会被 gate 拦下。

这一版有什么：[CHANGELOG.md](../CHANGELOG.md)。

## 许可

MIT —— 见 [LICENSE](../LICENSE)。
