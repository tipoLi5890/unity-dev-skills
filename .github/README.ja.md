# unity-dev-skills

[繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md) · **日本語** · [English](../README.md)

AI コーディングエージェント向けの Unity 6 ゲーム開発 skills。空のプロジェクトから検証済みの
成果物までを一巡りカバーする 32 個の skill で、Claude Code と OpenAI Codex のどちらにも
インストールできます。

単なる Unity のメモの寄せ集めと違う点が三つあります。

1. **自己完結しています。** 「先に別のものを入れてください」と言う skill はひとつもありません。
   それぞれの `Scope — what this skill does NOT do` の節を通じて互いに誘導し合うので、
   どこから入っても正しい skill にたどり着きます。
2. **各 skill は、自分のプロジェクトで実行する手順です。** 何を確認するか、どう確認するか、
   そしてそれを行うコード —— `scripts/` の Python、`resources/` の C# とシェーダのソース、
   `templates/` のまるごとコピーして使うファイル —— 打ち直すためのメモではありません。
3. **skills はトピックではなく読み込む状況で分割してあります。** `SKILL.md` は症状ルーティング表を
   持つルーターで、深い内容はそこから名指しされた `reference/` ファイルにあります。おかげで skill は
   その場面で必要なぶんだけを読み込みます。

## インストール

```bash
claude plugin marketplace add tipoLi5890/unity-dev-skills
claude plugin install unity-dev@unity-dev
```

Codex も同じツリーを読みます。`.agents/plugins/marketplace.json` を指定してください。plugin 単体なら
`.codex-plugin/plugin.json` です。どちらも Claude 形式の manifest から生成されるので、
違うことを言い出すことはありません。

skills をプロジェクトへ直接置くこともできます —— `skills/*` を `<プロジェクト>/.claude/skills/`
へコピーしてください。

## Skills 一覧

| グループ | Skill | 読み込むとき |
|---|---|---|
| **ターミナルと検証** | `unity-cli` | ターミナルから Unity を動かす：editor、ライセンス、template、CI、MCP、そして「リトライして良いのか」を示す exit code |
| | `unity-debug` | 目に見えない変更を検証したいとき —— そして計測結果を信じる前に、計測する側が本当のことを言っていると確かめたいとき |
| | `unity-play-harness` | エージェントが自分で動かして読み取れるゲームにする：一行の probe スナップショット、目的の瞬間から直接始めて「準備完了の集合」を待つ名前付き situation、タイムラインに記録して不変条件を検証する journey test、そして手触りの不満を再現可能なテストに変える方法 |
| | `unity-profiling` | 遅いフレーム・揺れるフレームの裏で何が動いているのか：Profiler ウィンドウを開かない counter、90 フレーム窓の median/p95/worst、作業量カウンタ、そして前後の比較表 |
| **初日** | `unity-new-project` | 後から直すと高くつく決定：editor バージョンの固定、`.meta`/LFS、UPM の tag 固定、IL2CPP/ARM64、asmdef の境界 |
| | `unity-game-brief` | Unity を触る前の最初の一時間：一行のアイデアを一枚の体験ブリーフにし、画像で見た目を固定し、制約からアーキテクチャ案を導き、テスト可能な不変条件として書き、人間が実際に遊べる一つのインタラクションを作る |
| **UI** | `unity-game-ui` | **UI の依頼はまずここから。** プロジェクトがどの UI システムを使っているか判定して振り分け、誰も書いていない領域 —— runtime の `OnGUI` HUD —— を自分で受け持ちます |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— そして uGUI が何も描かなくなる六つの原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— そして USS が黙って無視するプロパティ |
| **アセット** | `unity-3d-models` | 静的なプロップ：AI 生成メッシュを、Unity が目にする前にインポートして減面する |
| | `unity-2d-sprites` | スプライトシート、スライス、pivot、9-slice、コマ列を再生可能な `AnimationClip` に —— importer の内側にあるメタデータ |
| | `unity-2d-pixel-perfect` | ドット絵がぼける、カメラが動くとピクセルが這う、タイルの継ぎ目に髪の毛のような隙間 —— そして手元にあるのは `PixelPerfectCamera` という名の二つのコンポーネントのどちらなのか |
| | `unity-sprite-atlas` | 同じ draw call に載せたいスプライト：スクリプトからの V2 アトラス、パッキングとプラットフォーム設定、そして焼いたテクスチャがプレイヤーに届くまで |
| | `unity-tilemap` | 矩形・ヘックス・アイソメトリックの Tile Palette と、手持ちの地形シートから作る RuleTile |
| | `unity-rigged-character` | 操作できるキャラクター：原画 → image-to-3D → Mixamo → Avatar → Animator → ゲームプレイ用リグ |
| **AI アセット生成** | `codex-visual` | `codex` の画像モデルで 2D アートを生成し、一冊のアートバイブルと一枚のアンカーでスタイルを固定：グリッド一括生成、短いアニメーションを 1 枚のシートとして生成し計測済みのコマへ切り出して GIF プレビュー、クロマキー透過、サイズ正規化 |
| | `comfyui-asset-generation` | 自前の ComfyUI で音楽・効果音・MiniMax H3 動画を生成：一度に一件、`/history` だけを完了の証拠に、モデル切替前に `/free` |
| **ランタイム領域** | `unity-physics-3d` | 決して発火しない衝突や trigger、高速すり抜け、目の前にあるのに当たらない raycast |
| | `unity-navigation` | NavMesh、agent、障害物、link —— そして transform を誰が所有するかの決定 |
| | `unity-render-urp` | 設定したのに出てこないポストプロセス、モバイルで賄える範囲、Render Graph のレビュー |
| | `unity-audio` | メモリ、load type、サンプリングレート、mixer のコスト —— 再インポートの前に必ず報告します |
| | `unity-localization` | 複数言語での出荷と、実際に破綻する CJK フォントのパイプライン |
| **出荷** | `unity-android-release` | ビルドしたあとに**証明する**：成果物を読み返す、keystore と versionCode の規律 |
| | `unity-web-release` | WebGL/WebGPU のダウンロードサイズ、サーバのヘッダ、ブラウザのメモリ上限 |
| **バックエンドと収益化** | `unity-live-services` | そのビルドがどの環境と話しているか、鍵をどこに置くか、オフライン経路を先に設計する |
| | `unity-ugs` | Gaming Services の API 面：どのパッケージが何を提供するか、ほかのすべてが前提にする初期化順、Cloud Save のアクセスクラス、Cloud Code、Remote Config |
| | `unity-iap` | In-App Purchasing v5 を呼び出し単位で：ストア接続、pending/confirm の流れ、レシート、権利付与、復元 —— そして二重に付与される／まったく付与されない |
| | `unity-ads-levelplay` | LevelPlay のメディエーション：ネイティブ依存の解決、init より前の同意、リワード／インタースティシャル／バナーの広告ユニット、インプレッション単位の収益 |
| | `unity-monetization` | IAP と広告 SDK が出荷とぶつかる場所：merged manifest、ストアでの申告、レシート |
| | `unity-multiplayer` | 取り返しのつかない決定としてのトポロジー、加えてボイスチャットとマイクの奪い合い |
| | `unity-multiplayer-services` | Sessions：プレイヤーが同じゲームに入るまで —— join code、一覧から選べる部屋、クイックジョイン、チケットマッチメイキング、relay、ホスト移行、専用サーバ |
| | `unity-vivox` | ボイスとテキストチャットを呼び出し単位で：サインイン、group／echo／位置チャンネル、参加者一覧、ミュートと push-to-talk、マイク権限 |

## この repo で作業する

```bash
python3 tools/lint-skills.py            # frontmatter、name とディレクトリ名の一致、サイズ上限、実行ファイルの構文
python3 tools/check-consistency.py      # manifest の一致、外部依存の宣言
python3 tools/sync-codex-manifests.py   # Codex 用 manifest を再生成
claude plugin validate .                # manifest の形
```

`.claude-plugin/*` が正本です。`.codex-plugin/plugin.json` と
`.agents/plugins/marketplace.json` は**生成物です —— 手で編集しないでください。**

この repo の外にある plugin へのルーティングは**宣言された依存**として扱います。`tools/check-consistency.py` の
`COMPANIONS` に理由付きで追加してください。宣言のないものは gate で落ちます。

このリリースの内容：[CHANGELOG.md](../CHANGELOG.md)。

## ライセンス

MIT —— [LICENSE](../LICENSE) を参照してください。
