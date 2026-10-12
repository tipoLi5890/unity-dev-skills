# unity-dev-skills

**繁體中文** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [English](../README.md)

給 AI 編碼代理使用的 Unity 6 遊戲開發 skills。四十七個 skill，涵蓋從空專案到可驗證產物的完整迴圈，
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

| 分組 | Skill | 什麼時候載入 |
|---|---|---|
| **終端機與驗證** | `unity-cli` | 從終端機驅動 Unity：editor、授權、template、CI、MCP，以及能告訴你「重試是否誠實」的 exit code |
| | `unity-debug` | 你需要驗證一個看不見的改動 —— 並且在相信量測工具之前，先證明它說的是真話 |
| | `unity-play-harness` | 把遊戲做成 agent 能驅動、能讀懂的樣子：一行 probe 快照、直接開進某個時刻並等待「就緒集合」的具名 situation、取樣成時間線並斷言不變量的 journey test，以及把一句手感抱怨變成可重現的測試——3D 或 2D 遊戲皆可 |
| | `unity-profiling` | 慢幀或不穩定的幀背後到底在做什麼工作：不開 Profiler 視窗的 counter、90 幀視窗的 median/p95/worst、工作量計數，以及一張前後對照表 |
| | `unity-device-testing` | 在**真的手機**上做驗收（Android／iOS）：探針場景每次狀態變化印一行帶標籤的 log、驅動腳本對 log 斷言並替你點系統對話框、真人一次只做一個實體動作且由裝置端驗證、用 exit code 分開「真的失敗」和「測試工具壞了」 |
| | `unity-search` | 把「找一下／在哪裡／誰引用了它」變成一條 Unity Search 查詢：型別 filter、資料夾、label、`ref=` 關係、場景元件查詢 —— 先把查詢寫給你看，Editor 還活著時順手幫你開視窗 |
| **第一天** | `unity-new-project` | 事後補救很貴的決策：editor 版本釘死、`.meta`/LFS、UPM 釘 tag、IL2CPP/ARM64、asmdef 邊界 |
| | `unity-game-brief` | 動 Unity 之前的第一個小時：一行想法變成一頁體驗簡報、用圖鎖定視覺、由限制推導出架構提案、寫成可測試的不變量，以及一個人可以真的玩到的互動 |
| | `unity-gameplay` | **任何沒有指明視角的 gameplay 需求都從這裡開始。** 為專案做指紋辨識——2D 或 3D、投影、視角、移動模型——並把操控、相機、動畫與驗證導流到各自的 skill；並且擁有寫成限制條件的類型配方、由控制器數值推導出的關卡度量，以及附帶結束檢查的製作階段 |
| **3C —— 輸入、相機、角色** | `unity-input` | 讓 gameplay 只讀一個 struct、永遠不讀裝置的玩家輸入：涵蓋鍵盤、手把與觸控的 actions asset，按下在 `Update` 鎖存、在 `FixedUpdate` 只花用一次——解掉時有時無或連跳兩次的跳躍——再加上輸入緩衝、螢幕搖桿、指標瞄準與重新綁定 |
| | `unity-camera` | 會抖動、拍到關卡外面或穿牆的相機：抖動背後的那兩個時鐘、Cinemachine 的 2D 跟隨與房間 confiner、pixel-perfect 跟隨、第三人稱環繞與第一人稱 rig、震動與 blend、2.x → 3.x 名稱對照表，以及證明 rig 站得住的 journey |
| | `unity-animation` | 跟遊戲狀態對不上的 Animator——卡在某個狀態、攻擊自己播出來、hitbox 一直開著：每個參數只有一個寫入者、用腳本建出 blend tree 與 sprite 狀態圖、被打斷也不會漏的事件與攻擊視窗、IK、Timeline 交接、root motion |
| **2D 世界** | `unity-2d-controller` | 會沿斜坡滑下去、黏在牆上、每次跳的高度都不一樣的 2D 角色：向物理引擎詢問地面在哪裡的 kinematic 平台跳躍 motor——斜坡、單向與移動平台、coyote time、可變跳躍高度、衝刺、蹬牆跳——瞄準與移動分離的俯視自由移動、以 tween 呈現的格子步進、Animator 橋接，以及證明跳躍頂點、coyote 與緩衝的 journey |
| | `unity-physics-2d` | 永遠不觸發的 `OnCollisionEnter2D` 或 `OnTriggerEnter2D`、穿過 tilemap 牆的子彈、打到玩家自己的地面檢查、卡在 tile 接縫上的角色：用 Box2D 自己的詞彙寫成的分診階梯、雙邊探針，以及唯讀的場景稽核 |
| | `unity-2d-rendering` | 畫在錯誤前後順序的 sprite、毫無作用或讓整個畫面變黑的 `Light2D`：依優先順序排列的四個排序鍵、`SortingGroup`、俯視、等角與六角場景的 Y 排序、shadow caster、normal map、sprite mask 與視差圖層 |
| | `unity-2d-level` | 把 2D 關卡當成資料來組裝：可序列化的關卡畫進固定的 Tilemap 圖層堆疊、執行期改 tile、房間與門、接成無盡跑道的 chunk、Tiled 與 LDtk 匯入、SpriteShape 地形，以及逐關檢查可達性的種子生成 |
| | `unity-2d-grid` | 戰棋與方塊解謎在矩形、等角與六角網格上的棋盤邏輯，純 C#、不需要場景：六角 offset、axial 與 cube 轉換、移動範圍、A* 路徑、視線、單一佔位表、推動規則、回合順序、undo、指標對應到格子 |
| | `unity-2d-animation` | 用 2D Animation 與 PSD Importer 套件做骨骼式 2D 角色：把 PSB 匯入成 rig、先骨骼再幾何再權重、`SpriteSkin` 與 CPU 或 GPU 變形、執行期切換 Sprite Library 的造型與裝備、2D IK，以及一份 rig 成本的稽核 |
| **UI** | `unity-game-ui` | **任何 UI 需求都從這裡開始。** 偵測專案用的是哪套 UI 系統並導流；並且擁有沒人寫的那一塊 —— runtime `OnGUI` HUD |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— 以及 uGUI 什麼都畫不出來的六種原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— 以及 USS 會靜默忽略的那些屬性 |
| **資產** | `unity-3d-models` | 靜態道具：匯入 AI 生成的網格——在 Unity 看到它們之前先檢查，超出預算的才減面 |
| | `unity-2d-sprites` | Sprite sheet、切圖、pivot、9-slice、把一組逐格做成可播放的 `AnimationClip` —— 那些住在 importer 裡的中繼資料 |
| | `unity-2d-pixel-perfect` | 像素畫糊掉、鏡頭一動像素就爬、tile 之間出現髮絲縫 —— 以及你手上到底是哪一個叫 `PixelPerfectCamera` 的元件 |
| | `unity-sprite-atlas` | 該共用一次 draw call 的 sprite：用腳本產 V2 atlas、打包與平台設定，以及打包好的貼圖怎麼到玩家手上 |
| | `unity-tilemap` | 矩形、六角與等角網格的 Tile Palette，以及用手上現成的地形圖產出 RuleTile |
| | `unity-rigged-character` | 可操作的角色：原畫 → image-to-3D → Mixamo → Avatar → Animator → gameplay rig；Mixamo 綁不了的比例，改由 `blender-character-rig` 出 FBX 接手 |
| **AI 素材生成** | `codex-visual` | 用 `codex` 影像模型出 2D 美術，靠一份美術聖經與一張錨定圖鎖住風格：grid one-shot 整組、短動畫生成成一張 sprite sheet 再切成量測過的逐格並輸出 GIF 預覽、去背、尺寸正規化，並以幾何驗收閘門讀回交付檔的置中與尺寸 |
| | `comfyui-asset-generation` | 用自架 ComfyUI 出音樂、音效、MiniMax H3 影片與圖生 3D 道具：一次一件、只信 `/history`、換模型前先 `/free` |
| | `blender-character-rig` | 透過 MCP server 在執行中的 Blender 裡，替圖生 3D 角色綁骨架、做動畫：骨頭依量到的特徵點擺放、權重依位置計算、道具掛在手骨上、key 出一段 action、算出預覽，再把 FBX 重新匯入驗證 |
| **執行期領域** | `unity-physics-3d` | 永遠不觸發的碰撞或 trigger、高速穿透、明明在正前方卻打不到的 raycast |
| | `unity-navigation` | NavMesh、agent、障礙物、link —— 以及決定誰擁有 transform |
| | `unity-render-urp` | 設了卻不出現的後製、行動裝置負擔得起的子集、Render Graph 審查 |
| | `unity-urp-migration` | 把 Built-in 專案分五個帶閘的階段搬到 URP，每一階段都從存檔後的專案讀回來驗證；也用來診斷搬到一半的專案：整片洋紅、PPv2 轉成 Volume、從來沒重烤的 lightmap、`GrabPass`／`OnRenderImage` |
| | `unity-audio` | 記憶體、load type、取樣率、mixer 成本 —— 它會先報告再重新匯入 |
| | `unity-localization` | 用一種以上的語言出貨，以及真正會出錯的 CJK 字型管線 |
| **出貨** | `unity-android-release` | 建置完之後**證明**它：把產物讀回來、keystore 與 versionCode 紀律 |
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
