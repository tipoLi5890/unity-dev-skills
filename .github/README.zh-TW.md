# unity-dev-skills

**繁體中文** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [English](../README.md)

給 AI 編碼代理使用的 Unity 6 遊戲開發 skills。五十七個 skill，涵蓋做一款遊戲的每個階段，從概念到可驗證的建置，
可安裝到 Claude Code 或 OpenAI Codex。

有三件事讓它不只是一堆 Unity 筆記：

1. **它是自足的。** 沒有任何一個 skill 會叫你先去裝別的東西。它們透過各自的
   `Scope — what this skill does NOT do` 段落互相導流，所以不管你從哪個方向進來，都會落到對的那一個。
2. **每個 skill 都是一套在你自己的專案上執行的方法。** 要檢查什麼、怎麼檢查，以及負責做這些事的
   程式碼 —— `scripts/` 裡的 Python、`resources/` 裡的 C# 與 shader 原始碼、`templates/` 裡整份
   複製走的檔案 —— 不是要你重打一遍的筆記。
3. **Skills 是按載入情境拆分的，不是按主題。** 一份 `SKILL.md` 是帶著症狀路由表的路由器，
   深度內容放在它指名的 `reference/` 檔案裡，所以一個 skill 只會把當下情境需要的東西載進來。

## 安裝

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

Codex 讀的是同一份樹：把它指向 `.agents/plugins/marketplace.json`，只要 plugin 本身的話就指向
`.codex-plugin/plugin.json`。兩份都由 Claude 格式的 manifest 生成，所以不可能講出不一樣的話。

也可以把 skills 直接放進專案 —— 把 `skills/*` 複製到 `<專案>/.claude/skills/`。

## Skills 一覽

分組依照一款遊戲由上而下經過的製作階段排列。任何 gameplay 需求都從 `unity-gameplay` 開始：
它會讀懂專案，再導流到其他 skill。

| 分組 | Skill | 什麼時候載入 |
|---|---|---|
| **每個階段 —— 終端機與搜尋** | `unity-cli` | 從終端機驅動 Unity：editor、授權、template、CI、MCP，以及能告訴你「重試是否誠實」的 exit code |
| | `unity-search` | 把「找一下／在哪裡／誰引用了它」變成一條 Unity Search 查詢：型別 filter、資料夾、label、`ref=` 關係、場景元件查詢 —— 先把查詢寫給你看，Editor 還活著時順手幫你開視窗 |
| **概念** | `unity-game-brief` | 動 Unity 之前的第一個小時：一行想法變成一頁體驗簡報、用圖鎖定視覺、由限制推導出架構提案、寫成可測試的不變量，以及一個人可以真的玩到的互動 |
| | `unity-new-project` | 事後補救很貴的決策：editor 版本釘死、`.meta`/LFS、UPM 釘 tag、IL2CPP/ARM64、asmdef 邊界 |
| | `unity-gameplay` | **任何沒有指明視角的 gameplay 需求都從這裡開始。** 為專案做指紋辨識——2D 或 3D、投影、視角、移動模型——並把操控、相機、動畫與驗證導流到各自的 skill；並且擁有寫成限制條件的類型配方、由控制器數值推導出的關卡度量，以及附帶結束檢查的製作階段 |
| **3C 原型** | `unity-input` | 讓 gameplay 只讀一個 struct、永遠不讀裝置的玩家輸入：涵蓋鍵盤、手把與觸控的 actions asset，按下在 `Update` 鎖存、在 `FixedUpdate` 只花用一次——解掉時有時無或連跳兩次的跳躍——再加上輸入緩衝、螢幕搖桿、指標瞄準與重新綁定 |
| | `unity-camera` | 會抖動、拍到關卡外面或穿牆的相機：抖動背後的那兩個時鐘、Cinemachine 的 2D 跟隨與房間 confiner、pixel-perfect 跟隨、第三人稱環繞與第一人稱 rig、震動與 blend、2.x → 3.x 名稱對照表，以及證明 rig 站得住的 journey |
| | `unity-2d-controller` | 會沿斜坡滑下去、黏在牆上、每次跳的高度都不一樣的 2D 角色：向物理引擎詢問地面在哪裡的 kinematic 平台跳躍 motor——斜坡、單向與移動平台、coyote time、可變跳躍高度、衝刺、蹬牆跳——瞄準與移動分離的俯視自由移動、以 tween 呈現的格子步進、Animator 橋接，以及證明跳躍頂點、coyote 與緩衝的 journey |
| | `unity-3d-controller` | `isGrounded` 一直閃爍、沿斜坡滑下去、上不了台階、換個幀率跳的高度就不一樣的 3D 角色：只讓一個元件擁有 transform、用自己的 cast 找地面的 `CharacterController` motor——斜坡、台階、移動平台——讀同一個輸入 struct 的第三人稱、第一人稱、俯視與分道跑酷控制器、Animator 橋接，以及證明斜坡、台階、跳躍頂點與換道的 journey |
| | `unity-animation` | 跟遊戲狀態對不上的 Animator——卡在某個狀態、攻擊自己播出來、hitbox 一直開著：每個參數只有一個寫入者、用腳本建出 blend tree 與 sprite 狀態圖、被打斷也不會漏的事件與攻擊視窗、IK、Timeline 交接、root motion |
| | `unity-physics-2d` | 永遠不觸發的 `OnCollisionEnter2D` 或 `OnTriggerEnter2D`、穿過 tilemap 牆的子彈、打到玩家自己的地面檢查、卡在 tile 接縫上的角色：用 Box2D 自己的詞彙寫成的分診階梯、雙邊探針，以及唯讀的場景稽核 |
| | `unity-physics-3d` | 永遠不觸發的碰撞或 trigger、高速穿透、明明在正前方卻打不到的 raycast |
| | `unity-play-harness` | 把遊戲做成 agent 能驅動、能讀懂的樣子：一行 probe 快照、直接開進某個時刻並等待「就緒集合」的具名 situation、取樣成時間線並斷言不變量的 journey test，以及把一句手感抱怨變成可重現的測試——3D 或 2D 遊戲皆可 |
| **垂直切片 —— 2D 世界** | `unity-2d-level` | 把 2D 關卡當成資料來組裝：可序列化的關卡畫進固定的 Tilemap 圖層堆疊、執行期改 tile、房間與門、接成無盡跑道的 chunk、Tiled 與 LDtk 匯入、SpriteShape 地形，以及逐關檢查可達性的種子生成 |
| | `unity-2d-grid` | 戰棋與方塊解謎在矩形、等角與六角網格上的棋盤邏輯，純 C#、不需要場景：六角 offset、axial 與 cube 轉換、移動範圍、A* 路徑、視線、單一佔位表、推動規則、回合順序、undo、指標對應到格子 |
| | `unity-tilemap` | 矩形、六角與等角網格的 Tile Palette，以及用手上現成的地形圖產出 RuleTile |
| | `unity-2d-rendering` | 畫在錯誤前後順序的 sprite、毫無作用或讓整個畫面變黑的 `Light2D`：依優先順序排列的四個排序鍵、`SortingGroup`、俯視、等角與六角場景的 Y 排序、shadow caster、normal map、sprite mask 與視差圖層 |
| **垂直切片 —— 3D 世界** | `unity-3d-level` | 在美術存在之前就照尺寸蓋好的 3D 關卡：從尺寸表（門、走廊、台階、斜坡、跳躍間距）生成、以行走 journey 證明的 greybox、1/2/4 m 網格上的模組化套件、附 override 稽核的 prefab 結構、集中在同一個 layer 的碰撞代理、Terrain、沿 spline 的道路與跑道，以及 URP decal |
| | `unity-lighting` | 烘焙了卻沒變化、角色在烘焙過的牆邊一片黑、室內反射出天空、鏡頭一轉陰影就閃或幾公尺外陰影就斷掉：URP 上涵蓋燈光模式、烘焙、probe、陰影與環境光的症狀階梯、唯讀的場景稽核、會讀回結果的烘焙，以及手機負擔得起的子集 |
| | `unity-navigation` | NavMesh、agent、障礙物、link —— 以及決定誰擁有 transform |
| **垂直切片 —— 系統** | `unity-interaction` | 讓東西可以被使用——「按 E 開門」、在兩個物件之間閃來閃去的提示、開了兩次的閘門、隔著牆也能按的開關、被收集兩次的金幣：一份 `IInteractable` 契約、依視角找出候選並只保留一個選取目標的 interactor、一個提示、拾取物、開關、以狀態機寫成的閘門、上鎖的門、指標熱點，以及證明閘門只開一次的 journey |
| | `unity-combat` | 一次揮擊扣兩次血、每一幀都在命中的劍、一下扣光所有血量的尖刺、直接穿過哨兵的子彈：一個傷害 struct 與帶有陣營、無敵與「死亡是一種狀態」的接收者、hit 與 hurt 圖層、擁有揮擊 id 與命中清單的查詢式 hitbox（由動畫視窗開啟）、經由 motor 的擊退、每一步都做 cast 的投射物，以及寫成資料的彈幕——2D 與 3D 皆可 |
| | `unity-game-ai` | 隔著牆也看得到你、永遠不放棄追擊、在兩個狀態之間閃爍、每一幀都在 raycast 的敵人：有預算的感知、按 tick 做的決策、移動交給擁有 transform 的那一方——程式碼狀態機、小型行為樹、視野錐、聽覺與記憶、巡邏與追擊、2D 尋路、波次生成器、回合制的走法評分，以及證明哨兵看見之後才開始追的 journey |
| | `unity-scene-flow` | 回到主選單後 manager 變成兩份、卡在 90% 的讀取畫面、什麼都停不下來的暫停、壞掉的存檔：一個永不卸載並擁有各項服務的 Boot 場景、同時只有一個操作在進行的 additive 載入、暫停也是一種狀態的遊戲階段狀態機、帶遷移與原子寫入的版本化存檔、會重建的檢查點、物件池、ScriptableObject 設定 |
| **垂直切片 —— UI** | `unity-game-ui` | **任何 UI 需求都從這裡開始。** 偵測專案用的是哪套 UI 系統並導流；並且擁有沒人寫的那一塊 —— runtime `OnGUI` HUD |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— 以及 uGUI 什麼都畫不出來的六種原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— 以及 USS 會靜默忽略的那些屬性 |
| **量產 —— 資產** | `unity-3d-models` | 靜態道具：匯入 AI 生成的網格——在 Unity 看到它們之前先檢查，超出預算的才減面 |
| | `unity-rigged-character` | 可操作的角色：原畫 → image-to-3D → Mixamo → Avatar → Animator → gameplay rig；Mixamo 綁不了的比例，改由 `blender-character-rig` 出 FBX 接手 |
| | `unity-2d-sprites` | Sprite sheet、切圖、pivot、9-slice、把一組逐格做成可播放的 `AnimationClip` —— 那些住在 importer 裡的中繼資料 |
| | `unity-2d-animation` | 用 2D Animation 與 PSD Importer 套件做骨骼式 2D 角色：把 PSB 匯入成 rig、先骨骼再幾何再權重、`SpriteSkin` 與 CPU 或 GPU 變形、執行期切換 Sprite Library 的造型與裝備、2D IK，以及一份 rig 成本的稽核 |
| | `unity-2d-pixel-perfect` | 像素畫糊掉、鏡頭一動像素就爬、tile 之間出現髮絲縫 —— 以及你手上到底是哪一個叫 `PixelPerfectCamera` 的元件 |
| | `unity-sprite-atlas` | 該共用一次 draw call 的 sprite：用腳本產 V2 atlas、打包與平台設定，以及打包好的貼圖怎麼到玩家手上 |
| | `unity-audio` | 記憶體、load type、取樣率、mixer 成本 —— 它會先報告再重新匯入 |
| | `unity-localization` | 用一種以上的語言出貨，以及真正會出錯的 CJK 字型管線 |
| **量產 —— AI 素材生成** | `codex-visual` | 用 `codex` 影像模型出 2D 美術，靠一份美術聖經與一張錨定圖鎖住風格：grid one-shot 整組、短動畫生成成一張 sprite sheet 再切成量測過的逐格並輸出 GIF 預覽、去背、尺寸正規化，並以幾何驗收閘門讀回交付檔的置中與尺寸 |
| | `comfyui-asset-generation` | 用自架 ComfyUI 出音樂、音效、MiniMax H3 影片與圖生 3D 道具：一次一件、只信 `/history`、換模型前先 `/free` |
| | `blender-character-rig` | 透過 MCP server 在執行中的 Blender 裡，替圖生 3D 角色綁骨架、做動畫：骨頭依量到的特徵點擺放、權重依位置計算、道具掛在手骨上、key 出一段 action、算出預覽，再把 FBX 重新匯入驗證 |
| | `blender-retarget` | 把現成的動作 clip 套到在 Blender 裡綁好骨架的角色上：透過 Auto-Rig Pro 或純 bpy 的骨骼對照表，依兩邊的 rest pose 轉換每個旋轉 key、一份 clip 清單、局部修權重、帶 NLA 審閱軌的動作庫、每段 clip 都對手骨檢查的道具，以及重新開啟存檔來驗證的稽核 |
| **打磨與優化** | `unity-game-feel` | 沒有打擊感的命中、命中後整個遊戲停住不動、閃白之後一直白著的敵人、三十個拾取物播出三十個音效、停不下來的手把震動：每個 gameplay 事件一列有預算的回饋——由唯一擁有 `Time.timeScale` 的元件做 hit stop、會還原的閃白、不需要套件的擠壓與 tween、粒子、拖尾、有發聲數上限的池化音效、會停下來的震動 |
| | `unity-render-urp` | 設了卻不出現的後製、行動裝置負擔得起的子集、Render Graph 審查 |
| | `unity-urp-migration` | 把 Built-in 專案分五個帶閘的階段搬到 URP，每一階段都從存檔後的專案讀回來驗證；也用來診斷搬到一半的專案：整片洋紅、PPv2 轉成 Volume、從來沒重烤的 lightmap、`GrabPass`／`OnRenderImage` |
| | `unity-profiling` | 慢幀或不穩定的幀背後到底在做什麼工作：不開 Profiler 視窗的 counter、90 幀視窗的 median/p95/worst、工作量計數，以及一張前後對照表 |
| | `unity-scene-optimisation` | 效能 counter 已經指出成本之後該改什麼：各條 batching 路徑以及為什麼 GPU instancing 在 URP 下毫無作用、`LODGroup` 與 Mesh LOD、烘焙式與 GPU occlusion culling、逐 layer 的剔除距離、貼圖尺寸與 mipmap streaming、sprite 與粒子的 overdraw——每個手段先用一個視窗測試，再在同一個 counter 上讀回 |
| | `unity-debug` | 你需要驗證一個看不見的改動 —— 並且在相信量測工具之前，先證明它說的是真話 |
| **出貨** | `unity-device-testing` | 在**真的手機**上做驗收（Android／iOS）：探針場景每次狀態變化印一行帶標籤的 log、驅動腳本對 log 斷言並替你點系統對話框、真人一次只做一個實體動作且由裝置端驗證、用 exit code 分開「真的失敗」和「測試工具壞了」 |
| | `unity-android-release` | 建置完之後**證明**它：把產物讀回來、keystore 與 versionCode 紀律 |
| | `unity-ios-build` | 不開 Xcode，把 Unity 專案變成 iPhone 上跑著的 process：headless build、免簽章的編譯關卡、用這台 Mac 真正有的東西簽章、`devicectl` 安裝、console 是唯一的 log 管道、native `.mm` plugin 30 秒迭代 |
| | `unity-web-release` | WebGL/WebGPU 的下載量、伺服器標頭、瀏覽器記憶體上限 |
| **後端與商業** | `unity-live-services` | 這個 build 在跟哪個環境說話、金鑰該放哪、先設計離線路徑 |
| | `unity-ugs` | Gaming Services 的 API 表面：哪個套件提供什麼、其他一切都依賴的初始化順序、Cloud Save 的存取類別、Cloud Code、Remote Config |
| | `unity-iap` | 逐個呼叫寫 In-App Purchasing v5：連上商店、pending/confirm 流程、收據、權益、restore —— 以及內容給了兩次或一次都沒給 |
| | `unity-ads-levelplay` | LevelPlay 廣告中介：原生依賴解析、init 之前的同意流程、rewarded/interstitial/banner 廣告單元、單次曝光層級的營收 |
| | `unity-monetization` | IAP 與廣告 SDK 撞上出貨流程的地方：merged manifest、商店宣告、收據 |
| | `unity-multiplayer` | 拓撲是那個很貴的決定，加上語音聊天與麥克風競用 |
| | `unity-multiplayer-services` | Sessions：玩家怎麼進到同一場遊戲 —— join code、可瀏覽的房間列表、quick join、ticket 配對、relay、host 遷移、專用伺服器 |
| | `unity-vivox` | 逐個呼叫接語音與文字聊天：登入、group/echo/定位頻道、參與者名單、mute 與 push-to-talk、麥克風權限 |

## 在這個 repo 上工作

```bash
python3 tools/lint-skills.py            # frontmatter + name 與目錄名一致 + 大小上限 + 可執行檔語法
python3 tools/check-consistency.py      # manifest 一致、外部依賴已宣告
python3 tools/sync-codex-manifests.py   # 重新生成 Codex manifest
claude plugin validate .                # manifest 形狀
```

`.claude-plugin/*` 是事實來源。`.codex-plugin/plugin.json` 與 `.agents/plugins/marketplace.json`
是**生成物 —— 永遠不要手動編輯它們。**

路由到本 repo 以外的 plugin 算一項**宣告過的依賴**：把它加進 `tools/check-consistency.py` 的
`COMPANIONS`，並寫上理由。沒宣告的會被 gate 擋下。

這一版有什麼：[CHANGELOG.md](../CHANGELOG.md)。

## 授權

MIT —— 見 [LICENSE](../LICENSE)。
