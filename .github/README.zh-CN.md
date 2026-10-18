# unity-dev-skills

[繁體中文](README.zh-TW.md) · **简体中文** · [日本語](README.ja.md) · [English](../README.md)

面向 AI 编码代理的 Unity 6 游戏开发 skills。五十九个 skill，覆盖做一款游戏的每个阶段，从概念到可验证的构建，
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

分组按照一款游戏自上而下经历的制作阶段排列。任何 gameplay 需求都从 `unity-gameplay` 开始：
它会读懂项目，再导流到其他 skill。

| 分组 | Skill | 什么时候加载 |
|---|---|---|
| **每个阶段 —— 终端与搜索** | `unity-cli` | 从终端驱动 Unity：editor、许可、template、CI、MCP，以及能告诉你"重试是否诚实"的 exit code |
| | `unity-search` | 把"找一下／在哪里／谁引用了它"变成一条 Unity Search 查询：类型 filter、文件夹、label、`ref=` 关系、场景组件查询 —— 先把查询写给你看，Editor 还活着时顺手帮你打开窗口 |
| **概念** | `unity-game-brief` | 动 Unity 之前的第一个小时：一行想法变成一页体验简报、用图锁定视觉、由约束推导出架构提案、写成可测试的不变量，以及一个人能真的玩到的交互；写代码前先看到游戏：按游戏自己的规则常量合成、每个音效都记成事件的定时模拟游玩预览，再接成带片头卡、音乐与统一响度的 reel；第一个交互之后：只有人能关闭的里程碑关卡、多个 agent 各自的简报（`templates/AGENT_BRIEF.md`、`templates/DECISION_LOG.md`） |
| | `unity-new-project` | 事后补救代价很高的决策：editor 版本锁定、`.meta`/LFS、UPM 锁 tag、IL2CPP/ARM64、asmdef 边界；不开 Editor、几秒跑完不依赖引擎的测试（`scripts/pure_tests.py`），以及对照配额的 LFS 账本 |
| | `unity-gameplay` | **任何没有指明视角的 gameplay 需求都从这里开始。** 为项目做指纹识别——2D 或 3D、投影、视角、移动模型——并把操控、相机、动画与验证导流到各自的 skill；并且承担写成约束的类型配方、由控制器数值推导出的关卡度量，以及带有退出检查的制作阶段；球拍与球棒类游戏先测动作库、再定模拟数值，模拟跑在自己的线程、用绝对时钟（`SimHost.cs`、`SimClock.cs`） |
| **3C 原型** | `unity-input` | 让 gameplay 只读一个 struct、永远不读设备的玩家输入：覆盖键盘、手柄与触控的 actions asset，按下在 `Update` 锁存、在 `FixedUpdate` 只消费一次——解决时有时无或连跳两次的跳跃——再加上输入缓冲、屏幕摇杆、指针瞄准与重新绑定；以设备自己的时间戳、按毫秒评分的时机按压 |
| | `unity-camera` | 会抖动、拍到关卡外面或穿墙的相机：抖动背后的那两个时钟、Cinemachine 的 2D 跟随与房间 confiner、pixel-perfect 跟随、第三人称环绕与第一人称 rig、震动与 blend、2.x → 3.x 名称对照表，以及证明 rig 站得住的 journey；球场运动的转播式构图 |
| | `unity-2d-controller` | 会沿斜坡滑下去、粘在墙上、每次跳的高度都不一样的 2D 角色：向物理引擎询问地面在哪里的 kinematic 平台跳跃 motor——斜坡、单向与移动平台、coyote time、可变跳跃高度、冲刺、蹬墙跳——瞄准与移动分离的俯视自由移动、以 tween 呈现的格子步进、Animator 桥接，以及证明跳跃顶点、coyote 与缓冲的 journey |
| | `unity-3d-controller` | `isGrounded` 一直闪烁、沿斜坡滑下去、上不了台阶、换个帧率跳的高度就不一样的 3D 角色：只让一个组件拥有 transform、用自己的 cast 找地面的 `CharacterController` motor——斜坡、台阶、移动平台——读同一个输入 struct 的第三人称、第一人称、俯视与分道跑酷控制器、Animator 桥接，以及证明斜坡、台阶、跳跃顶点与换道的 journey |
| | `unity-animation` | 跟游戏状态对不上的 Animator——卡在某个状态、攻击自己播出来、hitbox 一直开着：每个参数只有一个写入者、用脚本构建 blend tree 与 sprite 状态图、被打断也不会丢的事件与攻击窗口、IK、Timeline 交接、root motion；跟着模拟走的手建 PlayableGraph、用 Animation Job 做的脚锁与道具 IK，以及会统计跳变的动作度量（C# 在 `resources/`） |
| | `unity-physics-2d` | 永远不触发的 `OnCollisionEnter2D` 或 `OnTriggerEnter2D`、穿过 tilemap 墙的子弹、打到玩家自己的地面检测、卡在 tile 接缝上的角色：用 Box2D 自己的词汇写成的分诊阶梯、双边探针，以及只读的场景审计 |
| | `unity-physics-3d` | 永远不触发的碰撞或 trigger、高速穿透、明明就在正前方却打不到的 raycast；游戏自己积分的运动用球，含旋转与扫掠碰撞（`BallFlight.cs`） |
| | `unity-play-harness` | 把游戏做成 agent 能驱动、能读懂的样子：一行 probe 快照、直接开进某个时刻并等待"就绪集合"的具名 situation、采样成时间线并断言不变量的 journey test，以及把一句手感抱怨变成可复现的测试——3D 或 2D 游戏皆可 |
| **垂直切片 —— 2D 世界** | `unity-2d-level` | 把 2D 关卡当成数据来组装：可序列化的关卡画进固定的 Tilemap 图层堆叠、运行时改 tile、房间与门、接成无尽跑道的 chunk、Tiled 与 LDtk 导入、SpriteShape 地形，以及逐关检查可达性的种子生成 |
| | `unity-2d-grid` | 战棋与方块解谜在矩形、等角与六角网格上的棋盘逻辑，纯 C#、不需要场景：六角 offset、axial 与 cube 转换、移动范围、A* 路径、视线、单一占位表、推动规则、回合顺序、undo、指针对应到格子 |
| | `unity-tilemap` | 矩形、六角与等角网格的 Tile Palette，以及用手上现成的地形图产出 RuleTile |
| | `unity-2d-rendering` | 画在错误前后顺序的 sprite、毫无作用或让整个画面变黑的 `Light2D`：按优先级排列的四个排序键、`SortingGroup`、俯视、等角与六角场景的 Y 排序、shadow caster、normal map、sprite mask 与视差图层 |
| **垂直切片 —— 3D 世界** | `unity-3d-level` | 在美术存在之前就按尺寸搭好的 3D 关卡：从尺寸表（门、走廊、台阶、斜坡、跳跃间距）生成、以行走 journey 证明的 greybox、1/2/4 m 网格上的模块化套件、附 override 审计的 prefab 结构、集中在同一个 layer 的碰撞代理、Terrain、沿 spline 的道路与跑道，以及 URP decal |
| | `unity-lighting` | 烘焙了却没变化、角色在烘焙过的墙边一片黑、室内反射出天空、镜头一转阴影就闪或几米外阴影就断掉：URP 上覆盖灯光模式、烘焙、probe、阴影与环境光的症状阶梯、只读的场景审计、会读回结果的烘焙，以及手机负担得起的子集 |
| | `unity-navigation` | NavMesh、agent、障碍物、link —— 以及决定谁拥有 transform |
| **垂直切片 —— 系统** | `unity-interaction` | 让东西可以被使用——"按 E 开门"、在两个物体之间闪来闪去的提示、开了两次的闸门、隔着墙也能按的开关、被收集两次的金币：一份 `IInteractable` 契约、按视角找出候选并只保留一个选中目标的 interactor、一个提示、拾取物、开关、用状态机写成的闸门、上锁的门、指针热点，以及证明闸门只开一次的 journey |
| | `unity-combat` | 一次挥击扣两次血、每一帧都在命中的剑、一下扣光所有血量的尖刺、直接穿过哨兵的子弹：一个伤害 struct 与带有阵营、无敌与"死亡是一种状态"的接收者、hit 与 hurt 图层、持有挥击 id 与命中列表的查询式 hitbox（由动画窗口开启）、经由 motor 的击退、每一步都做 cast 的投射物，以及写成数据的弹幕——2D 与 3D 皆可 |
| | `unity-game-ai` | 隔着墙也看得到你、永远不放弃追击、在两个状态之间闪烁、每一帧都在 raycast 的敌人：有预算的感知、按 tick 做的决策、移动交给拥有 transform 的那一方——代码状态机、小型行为树、视野锥、听觉与记忆、巡逻与追击、2D 寻路、波次生成器、回合制的走法评分，以及证明哨兵看见之后才开始追的 journey |
| | `unity-scene-flow` | 回到主菜单后 manager 变成两份、卡在 90% 的加载画面、什么都停不下来的暂停、损坏的存档：一个永不卸载并持有各项服务的 Boot 场景、同时只有一个操作在进行的 additive 加载、暂停也是一种状态的游戏阶段状态机、带迁移与原子写入的版本化存档、会重建的检查点、对象池、ScriptableObject 配置 |
| **垂直切片 —— UI** | `unity-game-ui` | **任何 UI 需求都从这里开始。** 检测项目使用的是哪套 UI 系统并导流；并且承担没人写的那一块 —— runtime `OnGUI` HUD |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— 以及 uGUI 什么都画不出来的六种原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— 以及 USS 会静默忽略的那些属性 |
| **量产 —— 资源** | `art-asset-registry` | 追踪每一件生成的 2D 与 3D 资源：每个项目一份只增不改的账本，记下 sha256 哈希（每个 `.blend` 版本也记）、来源血缘、指向美术规格与产出任务的链接、由人设定并附证据图的状态、上游改动后过期的资源，并以只读方式接手已有的 `manifest.md` |
| | `unity-3d-models` | 把 3D 模型带进游戏，按来源分路——图生 3D 的 GLB、FBX 角色、Blender 绑好的骨架、购买的素材包——检查、减面到类别的目标、导入并审计；类别的预算由人选定：同一件资源在每个生成预设各产一版，放进游戏场景比较，从来不是固定上限 |
| | `unity-rigged-character` | Unity 端的绑骨角色契约，不论 FBX 从哪条路线来——Auto-Rig Pro、Blender 骨架、Mixamo、自动绑骨服务：导入 → Avatar（在 Blender 重定向的 clip 用 Generic，游戏需要部位遮罩或 IK 时才用 Humanoid）→ Animator → gameplay rig，在 Optimize Game Objects 下保住道具 socket，并重建 FBX 丢掉的 PBR 贴图；套到动作包骨架上的角色以 Generic 导入（`SharedSkeletonClipImporter.cs`） |
| | `unity-2d-sprites` | Sprite sheet、切图、pivot、9-slice、把一组逐帧做成可播放的 `AnimationClip` —— 那些住在 importer 里的元数据 |
| | `unity-2d-animation` | 用 2D Animation 与 PSD Importer 包做骨骼式 2D 角色：把 PSB 导入成 rig、先骨骼再几何再权重、`SpriteSkin` 与 CPU 或 GPU 变形、运行时切换 Sprite Library 的造型与装备、2D IK，以及一份 rig 成本的审计 |
| | `unity-2d-pixel-perfect` | 像素画发虚、镜头一动像素就爬、tile 之间出现发丝缝 —— 以及你手上到底是哪一个叫 `PixelPerfectCamera` 的组件 |
| | `unity-sprite-atlas` | 该共用一次 draw call 的 sprite：用脚本产 V2 atlas、打包与平台设置，以及打包好的贴图怎么到玩家手上 |
| | `unity-audio` | 内存、load type、采样率、mixer 开销 —— 它会先报告再重新导入；在频率上限之下合成的音效，由 `scripts/spectrum_check.py` 检查 |
| | `unity-localization` | 用一种以上的语言发布，以及真正会出问题的 CJK 字体管线 |
| **量产 —— AI 素材生成** | `game-character-pipeline` | **从一张图做出绑骨角色，从这里开始。** 直到 Unity 里核准的角色为止的阶段顺序：先决定路线、质量目标与轨道（预览轨直接绑密网格，出货轨先定预算 → 游戏网格 → 只绑一次），再走 S0–S13，每个阶段标出负责的 skill 与进出关卡；动作全来自一套动作包时，把网格套到它的骨架上，clip 原样播放 |
| | `codex-visual` | 用 `codex` 图像模型出 2D 美术，靠一份美术圣经与一张锚定图锁住风格：grid one-shot 整组、短动画生成成一张 sprite sheet 再切成量测过的逐帧并输出 GIF 预览、去背、尺寸归一化，并以几何验收闸门读回交付文件的居中与尺寸；也画图生 3D 角色起手的四面图，只在数值检查通过时才合成的审阅表，以及按主题分页、每格标出来源路径并记下哈希的概览页 |
| | `comfyui-asset-generation` | 用自建 ComfyUI 出音乐、音效、MiniMax H3 视频与图生 3D 的道具和角色：一次一件、只信 `/history`、切模型前先 `/free`；四面图上传前先去背，调参前先把项目 graph 和官方模板逐项比对，生成预设当成阶梯来比较，没有一个是目标；由地面坐标画出关键帧的布局图并在生成前找出交叉的移动，以及地平线一动就退回关键帧的镜头闸门 |
| | `blender-character-rig` | 通过 MCP server 在运行中的 Blender 里，给图生 3D 角色绑骨架、做动画：骨骼按量到的特征点摆放、权重按位置计算、道具挂在手骨上、key 出一段 action、渲染出预览，再把 FBX 重新导入验证；同一批模块也能无头运行成带关卡的阶段：把动作包骨架套到网格、蒙皮 LOD、字节完全相同的 FBX |
| | `blender-retarget` | 把现成的动作 clip 套到在 Blender 里绑好骨架的角色上：通过 Auto-Rig Pro 或纯 bpy 的骨骼对照表，按两边的 rest pose 转换每个旋转 key、一份 clip 清单、局部修权重、带 NLA 审阅轨的动作库、每段 clip 都对手骨检查的道具，以及重新打开存盘文件来验证的审计；套骨架还是重定向，用测量对比决定（`scripts/clip_metrics.py`、`scripts/bakeoff_report.py`） |
| **打磨与优化** | `unity-game-feel` | 没有打击感的命中、命中后整个游戏停住不动、闪白之后一直白着的敌人、三十个拾取物播出三十个音效、停不下来的手柄震动：每个 gameplay 事件一行有预算的反馈——由唯一持有 `Time.timeScale` 的组件做 hit stop、会还原的闪白、不需要插件的挤压与 tween、粒子、拖尾、有发声数上限的池化音效、会停下来的震动；让又小又快的球在画面上看得清、走得顺（`MinScreenSize.cs`、`scripts/screen_smoothness.py`） |
| | `unity-render-urp` | 设了却不出现的后处理、移动端负担得起的子集、Render Graph 审查、会被验证去掉的材质关键字（`UrpMaterialValidation.cs`） |
| | `unity-urp-migration` | 把 Built-in 项目分五个带闸的阶段搬到 URP，每一阶段都从存盘后的项目读回来验证；也用来诊断搬到一半的项目：整片洋红、PPv2 转成 Volume、从来没重烤的 lightmap、`GrabPass`／`OnRenderImage` |
| | `unity-profiling` | 慢帧或不稳定的帧背后到底在做什么工作：不开 Profiler 窗口的 counter、90 帧窗口的 median/p95/worst、工作量计数，以及一张前后对照表；分阶段的 GC 分配与运行时资源泄漏（`GcAllocProbe.cs`、`OwnedAssets.cs`、一个浸泡测试） |
| | `unity-scene-optimisation` | 性能 counter 已经指出成本之后该改什么：各条 batching 路径以及为什么 GPU instancing 在 URP 下毫无作用、`LODGroup` 与 Mesh LOD、烘焙式与 GPU occlusion culling、逐 layer 的剔除距离、纹理尺寸与 mipmap streaming、sprite 与粒子的 overdraw——每个手段先用一个窗口测试，再在同一个 counter 上读回 |
| | `unity-debug` | 你需要验证一个看不见的改动 —— 并且在相信测量工具之前，先证明它说的是真话；多个 agent 共用一台机器时最多两个 Editor（`lanes.sh` 在 `MAX_UNITY` 排队） |
| **发布** | `unity-device-testing` | 在**真机**上做验收（Android／iOS）：探针场景每次状态变化打印一行带标签的 log、驱动脚本对 log 断言并替你点系统对话框、真人一次只做一个物理动作且由设备端验证、用 exit code 区分"真的失败"和"测试工具坏了" |
| | `unity-android-release` | 构建完之后**证明**它：把产物读回来、keystore 与 versionCode 纪律 |
| | `unity-ios-build` | 不打开 Xcode，把 Unity 项目变成 iPhone 上运行的进程：headless build、免签名的编译关卡、用这台 Mac 真正拥有的东西签名、`devicectl` 安装、console 是唯一的 log 通道、native `.mm` plugin 30 秒迭代 |
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
python3 tools/check-registry.py        # 资源账本的 selftest 与 fixture、预算表只存一份
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
