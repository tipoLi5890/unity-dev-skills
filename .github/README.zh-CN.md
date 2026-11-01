<div align="center">

<h1>unity-dev-skills</h1>

<p><b>让 Claude Code 和 Codex 像一位严谨的 Unity 开发者那样工作，并且每一步都拿出证据的 Unity 6 skills。</b></p>

<p><i>61 个 skill，从最初的想法一直到真机上的构建。</i></p>

<p>
<a href="../.claude-plugin/plugin.json"><img alt="版本" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FtipoLi5890%2Funity-dev-skills%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version&color=blue"></a>
<a href="https://github.com/tipoLi5890/unity-dev-skills/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/tipoLi5890/unity-dev-skills/actions/workflows/ci.yml/badge.svg"></a>
<a href="../LICENSE"><img alt="许可证：MIT" src="https://img.shields.io/badge/licence-MIT-green"></a>
<img alt="Unity 6" src="https://img.shields.io/badge/Unity-6-black?logo=unity">
<img alt="支持 Claude Code · Codex" src="https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex-d97757">
</p>

[繁體中文](README.zh-TW.md) · **简体中文** · [日本語](README.ja.md) · [English](../README.md)

<img src="media/hero.jpg" alt="上下两行，每行都是同一个角色依次经过四个 skill。上行是 2D：一张角色静态图、抠成透明背景的同一个角色、一条跑步循环的帧序列，以及在 Unity 场景里奔跑的 sprite。下行是 3D：另一位快递员的概念图、由它生成并按概念图重新上色的 3D 网格、骨架的关节标记点，以及摆出两个极限姿势的绑骨角色" width="100%">

</div>

## 试着这样问

| 你说 | 会发生什么 |
|---|---|
| “跑者的跳跃有时候按了没反应。” | `unity-input` 在 `Update` 里锁存每一次按键，在 `FixedUpdate` 里只消费一次，再用一个 journey 测试证明按一次就只跳一次 |
| “哨兵隔着墙也能看见跑者。” | `unity-game-ai` 用距离、角度和一次视线射线检测搭出视野锥；一个 journey 证明哨兵看见之后才开始追 |
| “第三个拾取物刷出来的时候会卡一下。” | `unity-profiling` 以 90 帧为一个窗口对那一刻采样（中位数、p95、最差值），读取工作量和 GC 计数器，并对比改动前后 |
| “把这张跑者的画稿做成能在 Unity 里跑起来的角色。” | `game-character-pipeline` 先定下质量目标和路线，再把 S0–S13 各阶段——多视图、3D、绑骨、动作、导入——交给各自负责的 skill，每一步都有闸门 |
| “给哨兵绑骨，他穿长大衣。” | `character-autorig` 走裙装路线：沿着大衣里的每条腿找到胯下，把大衣的权重分给臀部和两条大腿，深蹲时大衣若在两腿之间撕开，绑骨就判定不通过 |
| “写代码之前，先让我看看这趟送快递玩起来是什么样。” | `unity-game-brief` 用游戏自己的规则常量生成一段定时的模拟游玩预览，每个音效都记入日志 |
| “拿这张跑者的静态图给我做个走路循环。” | `sprite-from-video` 让视频模型把这张静态图原地走起来，每一帧都按模型实际画出的那种绿幕颜色来抠像，靠测量找出循环，再输出画布大小一致的逐帧图和 `frames.json` |
| “把这张守卫的画稿拆成图层，在 Unity 里绑好骨。” | `comfyui-asset-generation` 把图拆成每个会动的部位一层，补画手臂挡住的地方；`unity-2d-animation` 为 PSB 写入骨骼、网格和权重，不必进 Skinning Editor，长棍和盾牌跟着他的手走 |
| “帮我装到 iPhone 上，不用打开 Xcode。” | `unity-ios-build` 执行无头构建、一道编译闸门、用你的 Mac 上现有的凭据签名、通过 `devicectl` 安装，并读取 App 的控制台输出 |

## 安装

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

**Codex** 读取的是同一套目录：把它指向 `.agents/plugins/marketplace.json`；如果只要插件本身，就指向
`.codex-plugin/plugin.json`。这两份文件都由 Claude 格式的 manifest 生成，所以内容不可能对不上。

**也可以直接复制**：把 `skills/*` 复制到项目的 `<project>/.claude/skills/` 里。

### 环境要求

- **必需**：Claude Code 或 Codex；一个 Unity 6 项目；运行脚本需要 Python 3.10 或更高版本，读取图像或音频的脚本还需要
  NumPy 和 Pillow。
- **可选，仅用于资源与角色管线**：Blender，版本要在你所用的 Auto-Rig Pro 版本支持范围内（`character-autorig` 里有说明）；Auto-Rig Pro，
  Artell 开发的付费插件：请在 [Gumroad](https://artell.gumroad.com/l/auto-rig-pro) 或 [Superhive](https://superhivemarket.com/products/auto-rig-pro) 购买正版许可，这也支持它的开发与后续更新；可选的 AI 文件随许可提供，一份许可限一台设备；部署在 GPU 机器上的自建 ComfyUI；用于 2D 美术的 `codex` CLI；SciPy，`mesh-texture-paint` 和 `comfyui-asset-generation` 的部件、拆层与场景脚本都需要。
- **可选，用于视频**：ffmpeg，凡是要输出视频的功能都需要它（预览、集锦短片、由视频生成的 sprite）。
- **可选，用于设备**：iOS 需要一台装有 Xcode 15 或更高版本的 Mac；Android 需要 Android SDK。

在 Unity 里的工作用不到任何资源管线或视频工具；手机构建只需要该平台本来就要求的那些东西。

## 看看效果

### 写代码之前先看到游戏

<div align="center">
<img src="media/preview.gif" alt="俯视角的送快递游戏：跑者沿着三车道的路往上跑，捡起包裹，从哨兵旁边经过，趁一道闸门开着时穿过去，又在下一道闸门关上后撞了上去" width="400">
<p><sub>这趟送快递的模拟游玩预览，用的是游戏自己的美术。</sub></p>
</div>

[`unity-game-brief`](../skills/unity-game-brief/SKILL.md) →
[`codex-visual`](../skills/codex-visual/SKILL.md)

每一次拾取、每一道闸门的时间都取自游戏自己的规则常量，并作为事件记入日志，这时一行代码都还没写。

### 从一张静态图到在 Unity 里奔跑的 sprite

<div align="center">
<img src="media/sprites.gif" alt="左：绿幕上的跑者静态图。右：同一个跑者的四段透明动画在棋盘格背景上并排播放：待机、走路、跑步和跳跃" width="800">
<p><sub>一张绿幕静态图：只靠这张图做出带呼吸感的待机动画，走路、跑步和跳跃则从生成的视频中截取。</sub></p>
</div>

<div align="center">
<img src="media/keying.jpg" alt="同一张跑者头发和脸部的特写，用两种方式抠像：普通的绿幕抠像留下一圈亮绿色的边；sprite-from-video 留下干净的边缘" width="640">
<p><sub>普通的绿幕抠像会留下一圈绿边；<code>sprite-from-video</code> 按模型实际画出的那种绿色来抠像，并去掉溢色。</sub></p>
</div>

<div align="center">
<img src="media/unity.gif" alt="Unity 6 的 2D 场景：跑者 sprite 沿街奔跑，跳过三个锥桶，收集包裹，然后穿过一道闸门停下" width="720">
<p><sub>同一套 sprite 放进 Unity 6：跑者跳过每一个锥桶，收集每一个包裹，并穿过闸门。</sub></p>
</div>

[`codex-visual`](../skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`sprite-from-video`](../skills/sprite-from-video/SKILL.md) →
[`unity-2d-sprites`](../skills/unity-2d-sprites/SKILL.md) →
[`unity-2d-controller`](../skills/unity-2d-controller/SKILL.md)

### 从灰暗的生成贴图，到与概念图一致的贴图

<div align="center">
<img src="media/texture.gif" alt="四栏转台：图生 3D 烘出贴图的跑者、重新上色后的同一个跑者，接着是烘出贴图与重新上色的快递背包。重新上色的版本颜色更亮更干净，脸、手套、背带和缝线等细节也更清楚" width="800">
<p><sub>同样的网格、同样的 UV。每组左边是图生 3D 烘出的贴图，右边是按概念图重新上色的贴图。</sub></p>
</div>

<div align="center">
<img src="media/texture-steps.jpg" alt="同一个机位的五格：背面概念图、未贴图的网格、交给模型的渲染图（已上色的部分显示颜色，其余用烘出的贴图作先验）、模型重画的结果，以及投影回贴图后的网格" width="800">
<p><sub>循环中的一步：渲染当前已上色的样子，让本地图像编辑模型按概念图重画这个视角，通过闸门后投影回 UV 贴图，再挑下一个机位。</sub></p>
</div>

[`codex-visual`](../skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`mesh-texture-paint`](../skills/mesh-texture-paint/SKILL.md)

图生 3D 的形状做得好，颜色却浑浊。这里保留网格、UV 和烘好的法线与 AO 贴图，只在你自己的 ComfyUI 上
一个机位一个机位地重画 base color。每个视角写进贴图前都要和渲染图比对（轮廓、多人拼贴、颜色漂移、
背景发白），头部另有近拍，让脸更清楚。

### 从一张画稿到一个会动、绑好骨架的角色

<div align="center">
<img src="media/motion.gif" alt="上：机器生成的角色双机位视频，分别是正面和侧面。下：由这段视频解算出的动作驱动角色的骨架" width="640">
<p><sub>上：生成的双机位视频。下：角色的骨架，由从视频中解算出的动作驱动。</sub></p>
</div>

[`codex-visual`](../skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`mesh-texture-paint`](../skills/mesh-texture-paint/SKILL.md) →
[`character-autorig`](../skills/character-autorig/SKILL.md) →
[`humanoid-motion`](../skills/humanoid-motion/SKILL.md) →
[`unity-rigged-character`](../skills/unity-rigged-character/SKILL.md)

3D 模型、骨架和动作都在你自己的机器上完成；只有 2D 美术会经过 `codex` CLI。双机位解算移植自
[anymove](https://github.com/patch-gg/anymove)（Apache-2.0；见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)）。sprite 片段和动作视频都由 MiniMax H3 机器生成，基于其开放权重在本地运行，遵循 MiniMax H3 Community License Agreement。

### 跟着奔跑摆动的背包和兜帽

<div align="center">
<img src="media/secondary.gif" alt="快递跑者的背影，左右并排两次，依次跑步、换车道、跳跃、停下、转身。左边关闭骨链：背包、兜帽和头发跟身体一起僵硬地移动。右边开启骨链：背包和兜帽在每次转向时摆动、滞后，停下后再慢慢静止" width="640">
<p><sub>同一套骨架、同一段动作，在 Unity 中。左：关闭骨链。右：开启弹簧骨链。</sub></p>
</div>

<div align="center">
<img src="media/secondary.jpg" alt="跑者开始转身时的一帧，左右并排。左边关闭骨链：背包停在蒙皮时的位置。右边开启骨链：背包甩向脊柱，滞后于转身" width="640">
<p><sub>转身的头几帧：开启骨链时，背包滞后于身体。</sub></p>
</div>

[`character-autorig`](../skills/character-autorig/SKILL.md) →
[`unity-rigged-character`](../skills/unity-rigged-character/SKILL.md)

绑骨步骤为背包、兜帽、头发、外套下摆和短裤加上骨链（其他角色身上则是腰包、长大衣的下摆或披风），并把每条的硬度和身体的位置写进 `<name>.secondary.json`。在 Unity 里一条命令就把它们变成弹簧骨，在任何帧率下都保持长度、不穿进身体。

### 近看也经得住的脸和手

<div align="center">
<img src="media/parts.jpg" alt="同一个快递跑者的三个版本左右并排，各有一张全身正面、一张脸部特写和一张右手特写。左边是整个身体一次图生 3D：脸部糊成一片，头发是一大块，手套里的手指粘成一块。中间是同一个身体，头部单独生成、头发拆开：眼睛、鼻子、嘴巴和耳朵更清楚，发束更细，但手还是粘在一起。右边连双手也单独生成、接进袖口，画上去的眼睛后面放了眼球：橙色露指手套里有四根分开的手指" width="800">
<p><sub>左：整个身体一次生成。中：头部单独生成。右：双手也单独生成，加上会转动的眼球。</sub></p>
</div>

[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`blender-character-rig`](../skills/blender-character-rig/SKILL.md) →
[`character-autorig`](../skills/character-autorig/SKILL.md)

脸部重要的角色，头部会按概念图以自己的比例重绘，作为独立部件生成，再装回全身网格上，比例仍以全身为准。头发拆成第三个网格，脖子的接缝藏进衣领并对齐肤色，绑骨步骤再把头发绑到头上。要近看手时，每只手单独生成、手指之间留空，再接进袖口，绑骨时每根手指都找得到；画上去的眼睛后面放进眼球，跟着眼骨转动。做游戏版时，各部件合并成一个网格、一张贴图图集，只需一次绘制调用。

### 长大衣和 Q 版身材，走同一套绑骨

<div align="center">
<img src="media/coat.jpg" alt="穿长大衣的哨兵，未上贴图，做深蹲和高踢腿，各有正面和侧面，分成上下两排。上排：大衣的左右两半各自跟着自己的大腿，深蹲时两腿之间裂开，踢腿时被扯开。下排：同样的姿势，大衣完整盖住两条大腿，下摆跟着抬起的腿走" width="800">
<p><sub>上：大衣像裤子那样分配权重，在两腿之间撕开。下：走裙装路线，大衣保持完整，下摆跟着每条腿走。</sub></p>
</div>

<div align="center">
<img src="media/chibi.jpg" alt="Q 版快递吉祥物，大头、戴帽子、连指手套、腰间挎着小包：先是上色版，接着是绑骨检查里未上贴图的四个姿势：双手高举、侧面深蹲、单膝高抬，以及双手握起连指手套" width="800">
<p><sub>头部占身高三分之一的 Q 版吉祥物：举手、深蹲、抬膝、握起连指手套，手套整片一起弯。</sub></p>
</div>

[`game-character-pipeline`](../skills/game-character-pipeline/SKILL.md) →
[`character-autorig`](../skills/character-autorig/SKILL.md) →
[`unity-rigged-character`](../skills/unity-rigged-character/SKILL.md)

身材类型在一开始由人决定。长大衣或裙子走裙装路线（`--body skirt`）：绑骨会沿着大衣里的每条腿找到胯下，把大衣的权重分给臀部和两条大腿，下摆另外加上自己的弹簧骨链，大衣若在两腿之间撕开就判定不通过。Q 版走自己的路线（`--body chibi`），大头、短脖子、粗四肢各有自己的测量范围和窗口，门槛不变；连指手套会被当成一整片来读、一整片来弯。绑骨的每一次改动都要经过一份绑骨考卷评分：已知关节位置的种子身体，加上故意埋入、每道闸门都必须抓到的错误。

### 自己绑好骨的分层 2D 跑者

<div align="center">
<img src="media/layered2d.gif" alt="Unity 里的两段画面。先是 2D 快递跑者的正面，左边是全身，右边是脸部特写：他在呼吸、眨眼、说话。接着是同一个跑者的侧面画法，沿着一条街奔跑，天空和天际线比店面和马路滚动得慢，邮筒、垃圾桶、消防栓和交通锥从前景经过，同一个不会连着出现两次" width="640">
<p><sub>一张正面、一张侧面的图，拆成图层后在 Unity 绑好骨：正面眨眼和说话，侧面在视差街景上奔跑。</sub></p>
</div>

<div align="center">
<img src="media/layered2d.jpg" alt="2D 快递跑者的六格画面。正面原图；同一张图拆成图层，叠上骨骼和关节线；接着是绑好骨的角色在 Unity 里的四个姿势：举起一只手、转头、举起双手并转头下蹲，以及迈步中的侧面" width="800">
<p><sub>原图、它的图层和骨骼，以及在 Unity 里摆出原图没画过的姿势的绑骨角色。</sub></p>
</div>

[`codex-visual`](../skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`unity-2d-animation`](../skills/unity-2d-animation/SKILL.md) →
[`unity-2d-rendering`](../skills/unity-2d-rendering/SKILL.md)

图在你自己的 ComfyUI 上拆成每个会动的部位一层，手臂和头发挡住的地方由 Qwen-Image-Edit 补画，Unity 再为 PSB 写入骨骼、网格和权重，不必进 Skinning Editor；街景由 Qwen-Image-Layered 按深度拆层（两者都是 Apache-2.0），做成视差滚动，道具不会和自己的副本并排。同一套图层也会输出成 Live2D Cubism 可直接导入的 PSD，再由人在 Cubism Editor 里按 Live2D 自己的许可绑定。

### 2D 绑骨上的道具和滑板

<div align="center">
<img src="media/guard.gif" alt="Unity 里侧面的 2D 街头守卫，前手握着长棍，后臂挂着圆盾：他在呼吸、挥棍攻击，接着竖着长棍奔跑，盾牌在手臂后面保持完整" width="339"> <img src="media/skate.gif" alt="Unity 里侧面的 2D 快递员，戴帽子、穿连帽外套，踩着滑板：后脚蹬地再踩回板上，接着蹲低做出 ollie，滑板带着两只脚一起升起" width="281">
<p><sub>左：守卫的长棍和盾牌各是独立图层，跟着他的手走。右：快递员的滑板有自己的骨骼，腿部 IK 让两只脚在蹬地和 ollie 时都踩在板上。</sub></p>
</div>

[`codex-visual`](../skills/codex-visual/SKILL.md) →
[`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) →
[`unity-2d-animation`](../skills/unity-2d-animation/SKILL.md)

道具在拆图时就先命名。拿在手上的道具成为那只手上的独立图层，被手臂挡住的部分按它自己的形状补全（圆盾用拟合出的椭圆）；踩在双脚下的滑板有自己的骨骼，两段式腿部 IK 让双脚一直踩在上面。拆图有闸门把关（道具不能留下缺口、滑板要在两只鞋底下），Unity 里的姿势也有：脚不能踩空，也不能陷进地面。

## 工作原理

```mermaid
flowchart LR
    A["你的需求"] --> B["SKILL.md<br/>症状表"]
    B --> C["reference/<br/>只加载需要的部分"]
    C --> D["scripts/ · resources/ · templates/"]
    D --> E{"闸门<br/>退出码 + 证据"}
    E -->|未通过| C
    E -->|通过| F["完成，并附上证据"]
```

- **听懂你的描述，找到对的方法**：每个 skill 开头都有一张用日常语言写成的症状表，另有四个“从这里开始”的
  skill 负责分派任何玩法、UI、角色或后端需求。
- **跑的是代码，不是建议**：130 多个 Python 脚本、200 多个 C# 文件和 50 多个模板，直接复制进你的项目，不用照着笔记重敲。
- **拿出证据**：每个方法最后都有一项你能读懂的检查，比如探针快照、journey 测试、重新导入的 FBX、设备日志。
- **占用上下文少，自成一体**：`SKILL.md` 只负责路由，深入的内容等情况需要时才加载。不需要任何其他插件：skill 之间通过各自的 Scope 段落互相交接。少数绑骨与动作脚本会调用相邻 skill 的脚本，清单见 [`tools/cross-skill-deps.txt`](../tools/cross-skill-deps.txt)，这些 skill 要一起安装。

## Skill 一览

> [!TIP]
> 不知道从哪里开始？任何玩法需求用 `unity-gameplay`，任何 UI 需求用 `unity-game-ui`，从一张图做出绑骨角色用 `game-character-pipeline`，任何后端、联机或商业化需求用 `unity-live-services`。

<details>
<summary><b>所有阶段——终端与搜索</b>：Unity CLI，以及在项目里查找任何东西</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-cli`](../skills/unity-cli/SKILL.md) | 在终端里使用 Unity，退出码会告诉你这次重试是否站得住脚 |
| [`unity-search`](../skills/unity-search/SKILL.md) | “它在哪？谁引用了它？”用一条 Unity Search 查询来回答 |

</details>

<details>
<summary><b>概念</b>：简报、第一天的项目设置、玩法分派</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-game-brief`](../skills/unity-game-brief/SKILL.md) | 把一个想法变成一份简报、一套锁定的视觉风格、一段玩法预览和一个可玩的交互 |
| [`unity-new-project`](../skills/unity-new-project/SKILL.md) | 第一天就该定下、事后补救代价很高的决定，以及不开 Editor 也能跑的测试 |
| [`unity-gameplay`](../skills/unity-gameplay/SKILL.md) | 任何玩法需求都**从这里开始**：它先给项目做指纹识别，再分派工作 |

</details>

<details>
<summary><b>3C 原型</b>：输入、相机、2D 与 3D 控制器、动画、物理、play harness</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-input`](../skills/unity-input/SKILL.md) | 跳跃有时按了没反应，或者一下跳两次；玩法代码只读一个输入 struct |
| [`unity-camera`](../skills/unity-camera/SKILL.md) | 相机抖动、拍到关卡外面，或者穿墙 |
| [`unity-2d-controller`](../skills/unity-2d-controller/SKILL.md) | 2D 角色沿斜坡往下滑或者粘在墙上：一个 kinematic motor |
| [`unity-3d-controller`](../skills/unity-3d-controller/SKILL.md) | `isGrounded` 忽真忽假，或者跳跃高度随帧率变化：一个 3D motor |
| [`unity-animation`](../skills/unity-animation/SKILL.md) | Animator 卡在某个状态，或者攻击动画自己播了出来 |
| [`unity-physics-2d`](../skills/unity-physics-2d/SKILL.md) | 永远不触发的 2D 碰撞或 trigger，用 Box2D 自己的术语排查 |
| [`unity-physics-3d`](../skills/unity-physics-3d/SKILL.md) | 永远不触发的碰撞或 trigger，或者由游戏自己积分运动的球 |
| [`unity-play-harness`](../skills/unity-play-harness/SKILL.md) | 让游戏能被驱动：一行探针快照，以及断言不变量的 journey 测试 |

</details>

<details>
<summary><b>垂直切片——2D 世界</b>：数据化的关卡、网格棋盘、Tile Palette、绘制顺序与 2D 灯光</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-2d-level`](../skills/unity-2d-level/SKILL.md) | 把 2D 关卡当作数据，带种子的生成会检查每个拾取物都能到达 |
| [`unity-2d-grid`](../skills/unity-2d-grid/SKILL.md) | 方形、等距或六角网格上的战棋与方块解谜棋盘逻辑 |
| [`unity-tilemap`](../skills/unity-tilemap/SKILL.md) | 画的时候 tile 接不起来：用你自己的图生成 RuleTile，每个网格一套 palette |
| [`unity-2d-rendering`](../skills/unity-2d-rendering/SKILL.md) | sprite 被错误地画到了另一张后面、`Light2D` 让整个画面变黑，或者视差背景 |

</details>

<details>
<summary><b>垂直切片——3D 世界</b>：按度量搭白盒、URP 光照、NavMesh agent</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-3d-level`](../skills/unity-3d-level/SKILL.md) | 按度量表搭出的 3D 白盒，并用一段行走 journey 来证明 |
| [`unity-lighting`](../skills/unity-lighting/SKILL.md) | URP 上烘焙了却没有变化，或者角色在烘焙过的墙边一片黑 |
| [`unity-navigation`](../skills/unity-navigation/SKILL.md) | agent 不动或者穿墙：NavMesh、link，以及 transform 归谁管 |

</details>

<details>
<summary><b>垂直切片——系统</b>：门与拾取物、伤害、敌人 AI、场景与存档</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-interaction`](../skills/unity-interaction/SKILL.md) | “按 E 开门”的提示闪来闪去，或者门开了两次：一个目标，一个提示 |
| [`unity-combat`](../skills/unity-combat/SKILL.md) | 一次挥砍打中两次，或者子弹直接穿过哨兵：每次只算一次命中 |
| [`unity-game-ai`](../skills/unity-game-ai/SKILL.md) | 能隔着墙看见你，或者永远不放弃追击的敌人：有预算的感知 |
| [`unity-scene-flow`](../skills/unity-scene-flow/SKILL.md) | manager 重复出现，或者存档损坏：一个 Boot 场景，加上带版本号的原子存档 |

</details>

<details>
<summary><b>垂直切片——UI</b>：UI 分派与 HUD、uGUI、UI Toolkit</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-game-ui`](../skills/unity-game-ui/SKILL.md) | 任何 UI 需求都**从这里开始**：它会识别项目用的是哪套 UI 系统，再分派 |
| [`unity-ui-ugui`](../skills/unity-ui-ugui/SKILL.md) | Canvas UI 什么都不显示：先做六项检查，再看锚点和 Layout Group |
| [`unity-ui-toolkit`](../skills/unity-ui-toolkit/SKILL.md) | USS 属性悄无声息地不起作用，以及 UXML、flex 布局与数据绑定 |

</details>

<details>
<summary><b>量产——资源</b>：资源账本、3D 模型、绑骨角色、sprite、音频、多语言</summary>

| Skill | 什么时候用 |
|---|---|
| [`art-asset-registry`](../skills/art-asset-registry/SKILL.md) | 每个生成的资源从哪来、哪些已经过期：一份只增不改的账本 |
| [`unity-3d-models`](../skills/unity-3d-models/SKILL.md) | 把 3D 模型放进游戏，预算在游戏相机下挑选 |
| [`unity-rigged-character`](../skills/unity-rigged-character/SKILL.md) | 绑骨的 FBX 在 Unity 里一直摆着 T-pose：导入、Avatar、Animator 与 gameplay rig |
| [`unity-2d-sprites`](../skills/unity-2d-sprites/SKILL.md) | 用脚本切 sprite sheet，再把逐帧做成可播放的 clip |
| [`unity-2d-animation`](../skills/unity-2d-animation/SKILL.md) | 由 PSB 做出骨骼式 2D 角色，用脚本绑骨，含道具和腿部 IK；运行时切换皮肤和装备 |
| [`unity-2d-pixel-perfect`](../skills/unity-2d-pixel-perfect/SKILL.md) | 像素画显示发虚、镜头一动就闪烁，或者出现接缝 |
| [`unity-sprite-atlas`](../skills/unity-sprite-atlas/SKILL.md) | 本该共用一次 draw call 的 sprite，用脚本打包成 V2 图集 |
| [`unity-audio`](../skills/unity-audio/SKILL.md) | 削减音频的内存和 CPU 开销，又不让游戏听起来变差；重新导入之前先出报告 |
| [`unity-localization`](../skills/unity-localization/SKILL.md) | 用不止一种语言发布，包括容易出问题的 CJK 字体管线 |

</details>

<details>
<summary><b>量产——AI 资源生成</b>：角色的阶段顺序、2D 美术、音频、视频与 3D、绑骨与动作</summary>

| Skill | 什么时候用 |
|---|---|
| [`game-character-pipeline`](../skills/game-character-pipeline/SKILL.md) | 用一张图做绑骨角色，**从这里开始**：S0–S13 各阶段，每一阶段都有闸门 |
| [`codex-visual`](../skills/codex-visual/SKILL.md) | 通过 `codex` 图像模型出 2D 美术，用一份美术圣经保持风格统一 |
| [`comfyui-asset-generation`](../skills/comfyui-asset-generation/SKILL.md) | 用你自己的 ComfyUI 出音乐、音效、视频、3D 模型和分层 2D 美术，每种各一个任务 |
| [`mesh-texture-paint`](../skills/mesh-texture-paint/SKILL.md) | 依照概念图逐个视角重绘生成 3D 模型暗淡的贴图，网格和 UV 保持不变 |
| [`sprite-from-video`](../skills/sprite-from-video/SKILL.md) | 通过一段生成的视频，把一张角色静态图变成透明的 sprite 循环 |
| [`blender-character-rig`](../skills/blender-character-rig/SKILL.md) | `character-autorig` 不适用时在 Blender 里手工绑骨，导出的 FBX 用重新导入来验证 |
| [`blender-retarget`](../skills/blender-retarget/SKILL.md) | 把现成的动作 clip 套到你的 Blender 骨架上，按脚滑、抖动和跳变把关 |
| [`character-autorig`](../skills/character-autorig/SKILL.md) | 用你自己的 Auto-Rig Pro 在本地给人形角色绑骨，长大衣和 Q 版也行，一条命令完成；可选的 AI 检测会打开一个 Blender 窗口 |
| [`humanoid-motion`](../skills/humanoid-motion/SKILL.md) | 把一个动作做成 clip，从双机位视频直接解算到骨架上 |

</details>

<details>
<summary><b>打磨与优化</b>：游戏手感、URP、迁移、性能分析、场景开销、验证</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-game-feel`](../skills/unity-game-feel/SKILL.md) | 命中没有打击感：每个玩法事件一行反馈，并且有预算 |
| [`unity-render-urp`](../skills/unity-render-urp/SKILL.md) | 就是不出现的后处理，以及发布前审查 Render Graph 功能 |
| [`unity-urp-migration`](../skills/unity-urp-migration/SKILL.md) | 分五个带闸门的阶段从 Built-in 迁到 URP，或者诊断迁移到一半的项目 |
| [`unity-profiling`](../skills/unity-profiling/SKILL.md) | 一帧变慢或不稳时到底在做什么，以 90 帧窗口记录并对比 |
| [`unity-scene-optimisation`](../skills/unity-scene-optimisation/SKILL.md) | 计数器指出开销之后的修法，并在同一个计数器上读回结果 |
| [`unity-debug`](../skills/unity-debug/SKILL.md) | 验证一个你看不见的改动——前提是先证明 harness 说的是真话 |

</details>

<details>
<summary><b>发布</b>：真机测试、Android、iOS、Web</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-device-testing`](../skills/unity-device-testing/SKILL.md) | 在真机上验收：agent 负责驱动，真人只做物理操作的那一步 |
| [`unity-android-release`](../skills/unity-android-release/SKILL.md) | 签好名的 APK 或 AAB，通过读回产物来证明 |
| [`unity-ios-build`](../skills/unity-ios-build/SKILL.md) | 不打开 Xcode，把 Unity 项目变成在 iPhone 上运行的 App |
| [`unity-web-release`](../skills/unity-web-release/SKILL.md) | WebGL 或 WebGPU 构建足够小、足够快，让人愿意等它加载 |

</details>

<details>
<summary><b>后端与商业化</b>：后端规范、Gaming Services、内购、广告、多人联机、语音</summary>

| Skill | 什么时候用 |
|---|---|
| [`unity-live-services`](../skills/unity-live-services/SKILL.md) | 后端、联机与商业化的起点：离线路径、多人联机拓扑、SDK 与商店声明的接缝 |
| [`unity-ugs`](../skills/unity-ugs/SKILL.md) | 服务因为没有初始化而抛异常：按正确的顺序初始化 Gaming Services |
| [`unity-iap`](../skills/unity-iap/SKILL.md) | 内容发了两次或者一次都没发：逐个调用讲清 In-App Purchasing v5 |
| [`unity-ads-levelplay`](../skills/unity-ads-levelplay/SKILL.md) | 广告不出现，或者广告依赖把构建弄坏：LevelPlay，初始化之前先取得同意 |
| [`unity-multiplayer-services`](../skills/unity-multiplayer-services/SKILL.md) | 玩家怎么进到同一局游戏，从加入码到主机迁移 |
| [`unity-vivox`](../skills/unity-vivox/SKILL.md) | 进了语音频道却没人听得见：Vivox 聊天，从登录到按键说话 |

</details>

## 参与贡献

工具、检查和仓库规则：[.github/CONTRIBUTING.md](CONTRIBUTING.md)。每个版本包含哪些内容：[CHANGELOG.md](../CHANGELOG.md)。

## 许可证

MIT——见 [LICENSE](../LICENSE)。移植自其他项目的代码保留各自的许可证：[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
