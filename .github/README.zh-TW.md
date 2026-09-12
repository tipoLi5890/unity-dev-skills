# unity-dev-skills

**繁體中文** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [English](../README.md)

給 AI 編碼代理使用的 Unity 6 遊戲開發 skills。二十九個 skill，涵蓋從空專案到可驗證產物的完整迴圈，
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
| **第一天** | `unity-new-project` | 事後補救很貴的決策：editor 版本釘死、`.meta`/LFS、UPM 釘 tag、IL2CPP/ARM64、asmdef 邊界 |
| **UI** | `unity-game-ui` | **任何 UI 需求都從這裡開始。** 偵測專案用的是哪套 UI 系統並導流；並且擁有沒人寫的那一塊 —— runtime `OnGUI` HUD |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— 以及 uGUI 什麼都畫不出來的六種原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— 以及 USS 會靜默忽略的那些屬性 |
| **資產** | `unity-3d-models` | 靜態道具：在 Unity 看到它們之前，先匯入並減面 AI 生成的網格 |
| | `unity-2d-sprites` | Sprite sheet、切圖、pivot、9-slice、把一組逐格做成可播放的 `AnimationClip` —— 那些住在 importer 裡的中繼資料 |
| | `unity-2d-pixel-perfect` | 像素畫糊掉、鏡頭一動像素就爬、tile 之間出現髮絲縫 —— 以及你手上到底是哪一個叫 `PixelPerfectCamera` 的元件 |
| | `unity-sprite-atlas` | 該共用一次 draw call 的 sprite：用腳本產 V2 atlas、打包與平台設定，以及打包好的貼圖怎麼到玩家手上 |
| | `unity-tilemap` | 矩形、六角與等角網格的 Tile Palette，以及用手上現成的地形圖產出 RuleTile |
| | `unity-rigged-character` | 可操作的角色：原畫 → image-to-3D → Mixamo → Avatar → Animator → gameplay rig |
| **AI 素材生成** | `codex-visual` | 用 `codex` 影像模型出 2D 美術，靠一份美術聖經與一張錨定圖鎖住風格：grid one-shot 整組、短動畫生成成一張 sprite sheet 再切成量測過的逐格並輸出 GIF 預覽、去背、尺寸正規化 |
| | `comfyui-asset-generation` | 用自架 ComfyUI 出音樂、音效與 MiniMax H3 影片：一次一件、只信 `/history`、換模型前先 `/free` |
| **執行期領域** | `unity-physics-3d` | 永遠不觸發的碰撞或 trigger、高速穿透、明明在正前方卻打不到的 raycast |
| | `unity-navigation` | NavMesh、agent、障礙物、link —— 以及決定誰擁有 transform |
| | `unity-render-urp` | 設了卻不出現的後製、行動裝置負擔得起的子集、Render Graph 審查 |
| | `unity-audio` | 記憶體、load type、取樣率、mixer 成本 —— 它會先報告再重新匯入 |
| | `unity-localization` | 用一種以上的語言出貨，以及真正會出錯的 CJK 字型管線 |
| **出貨** | `unity-android-release` | 建置完之後**證明**它：把產物讀回來、keystore 與 versionCode 紀律 |
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
