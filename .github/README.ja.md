# unity-dev-skills

[繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md) · **日本語** · [English](../README.md)

AI コーディングエージェント向けの Unity 6 ゲーム開発 skills。コンセプトから検証済みのビルドまで、
ゲーム制作のすべての段階をカバーする 56 個の skill で、Claude Code と OpenAI Codex のどちらにも
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

グループは、ゲームが上から下へとたどる制作の段階順に並んでいます。gameplay の依頼はどれも
`unity-gameplay` から始めてください。プロジェクトを読み取り、残りの skill へ振り分けます。

| グループ | Skill | 読み込むとき |
|---|---|---|
| **全ステージ —— ターミナルと検索** | `unity-cli` | ターミナルから Unity を動かす：editor、ライセンス、template、CI、MCP、そして「リトライして良いのか」を示す exit code |
| | `unity-search` | 「探したい／どこにある／何が参照している」を一本の Unity Search クエリにする：型フィルタ、フォルダ、label、`ref=` の関係、シーンのコンポーネント検索 —— 実行する前にクエリを見せ、生きた Editor があれば検索ウィンドウも開きます |
| **コンセプト** | `unity-game-brief` | Unity を触る前の最初の一時間：一行のアイデアを一枚の体験ブリーフにし、画像で見た目を固定し、制約からアーキテクチャ案を導き、テスト可能な不変条件として書き、人間が実際に遊べる一つのインタラクションを作る |
| | `unity-new-project` | 後から直すと高くつく決定：editor バージョンの固定、`.meta`/LFS、UPM の tag 固定、IL2CPP/ARM64、asmdef の境界 |
| | `unity-gameplay` | **視点を指定していない gameplay の依頼はまずここから。** プロジェクトのフィンガープリント——2D か 3D か、投影、視点、移動モデル——を取り、操作・カメラ・アニメーション・検証をそれぞれの skill に振り分けます。制約として書かれたジャンル別レシピ、コントローラーの数値から導くレベルメトリクス、終了チェック付きの制作ステージを受け持ちます |
| **3C プロトタイプ** | `unity-input` | gameplay がデバイスではなく一つの struct だけを読むプレイヤー入力：キーボード・ゲームパッド・タッチ用の actions asset、押下を `Update` でラッチして `FixedUpdate` で一度だけ消費する仕組み——効いたり効かなかったり、二度発火したりするジャンプへの対処——に加え、入力バッファ、画面上スティック、ポインターエイム、リバインド |
| | `unity-camera` | ガタつく、レベルの外を映す、壁を突き抜けるカメラ：ガタつきの原因である二つのクロック、Cinemachine による 2D 追従とルーム confiner、pixel-perfect 追従、三人称オービットと一人称の rig、シェイクとブレンド、2.x → 3.x の名前対応表、そして rig が保たれることを証明する journey |
| | `unity-2d-controller` | 坂を滑り落ちる、壁に張り付く、跳ぶたびに高さが変わる 2D キャラクター：地面の位置を物理に問い合わせる kinematic なプラットフォーマー motor——坂、一方通行と動く足場、coyote time、可変ジャンプ、ダッシュ、壁ジャンプ——に加え、エイムと移動を分けた見下ろし自由移動、tween で見せるセル単位の移動、Animator ブリッジ、そして頂点・coyote・バッファを証明する journey |
| | `unity-3d-controller` | `isGrounded` がちらつく、坂を滑り落ちる、段差を上れない、フレームレートが変わると跳ぶ高さが変わる 3D キャラクター：transform を動かすのは一つのコンポーネントだけ、自前の cast で地面を見つける `CharacterController` の motor——坂、段差、動く足場——に、一つの入力 struct を読む三人称・一人称・見下ろし・レーンランナーのコントローラー、Animator ブリッジ、そして坂・段差・頂点・レーン変更を証明する journey |
| | `unity-animation` | ゲームの状態と食い違う Animator——ステートから抜けない、攻撃が勝手に再生される、hitbox が開いたまま：パラメーターごとに書き手は一つ、スクリプトから組む blend tree と sprite ステートグラフ、割り込まれても壊れないイベントと攻撃ウィンドウ、IK、Timeline の受け渡し、root motion |
| | `unity-physics-2d` | 決して発火しない `OnCollisionEnter2D` や `OnTriggerEnter2D`、tilemap の壁を抜ける弾、プレイヤー自身に当たる接地判定、tile の継ぎ目に引っかかるキャラクター：Box2D 自身の語彙で書かれたトリアージの手順、両側プローブ、読み取り専用のシーン監査 |
| | `unity-physics-3d` | 決して発火しない衝突や trigger、高速すり抜け、目の前にあるのに当たらない raycast |
| | `unity-play-harness` | エージェントが自分で動かして読み取れるゲームにする：一行の probe スナップショット、目的の瞬間から直接始めて「準備完了の集合」を待つ名前付き situation、タイムラインに記録して不変条件を検証する journey test、そして手触りの不満を再現可能なテストに変える方法——3D でも 2D でも |
| **バーティカルスライス —— 2D ワールド** | `unity-2d-level` | 2D レベルをデータとして組み立てる：固定の Tilemap レイヤースタックに描き込むシリアライズ可能なレベル、ランタイムでの tile 編集、部屋と扉、エンドレスランにつなぐ chunk、Tiled と LDtk のインポート、SpriteShape の地形、そしてレベルごとに到達可能性を検査するシード生成 |
| | `unity-2d-grid` | 矩形・アイソメトリック・ヘックスのグリッド上で動くタクティクスやタイルパズルの盤面ロジックを、シーン不要の素の C# で：ヘックスの offset・axial・cube 変換、移動範囲、A* 経路、射線、一つの占有マップ、押し出しルール、ターン順、undo、ポインターからセルへ |
| | `unity-tilemap` | 矩形・ヘックス・アイソメトリックの Tile Palette と、手持ちの地形シートから作る RuleTile |
| | `unity-2d-rendering` | 前後が逆に描かれる sprite、何も起きない、あるいは画面全体を黒くする `Light2D`：優先順位どおりの四つのソートキー、`SortingGroup`、見下ろし・アイソメトリック・ヘックスのシーン向け Y ソート、shadow caster、normal map、sprite mask、パララックスレイヤー |
| **バーティカルスライス —— 3D ワールド** | `unity-3d-level` | アートができる前に寸法どおりに組む 3D レベル：寸法表（扉、通路、段差、坂、ジャンプの間隔）から作り、歩行 journey で証明する greybox、1/2/4 m グリッド上のモジュラーキット、override 監査つきの prefab 構成、一つのレイヤーにまとめたコリジョン代理、Terrain、spline に沿った道とレーン、そして URP のデカール |
| | `unity-lighting` | ベイクしても何も変わらない、ベイクした壁の横でキャラクターが真っ黒、屋内に空が映り込む、カメラを回すと影がちらつく、数メートル先で影が切れる：URP でのライトモード・ベイク・プローブ・影・環境光をたどる症状別の手順、読み取り専用のシーン監査、結果を読み戻すベイク、そしてスマートフォンで賄える範囲 |
| | `unity-navigation` | NavMesh、agent、障害物、link —— そして transform を誰が所有するかの決定 |
| **バーティカルスライス —— システム** | `unity-interaction` | 物を使えるようにする——「E でドアを開ける」、二つの物の間でちらつくプロンプト、二度開くゲート、壁越しに押せてしまうスイッチ、二回拾われるコイン：一つの `IInteractable` 契約、視点に応じて候補を見つけ選択対象を一つだけ保つ interactor、一つのプロンプト、ピックアップ、スイッチ、ステートマシンとしてのゲート、鍵のかかったドア、ポインターのホットスポット、そしてゲートが一度だけ開くことを証明する journey |
| | `unity-combat` | 一振りで二回ダメージが入る、毎フレーム当たり続ける剣、一瞬で体力を削り切るトゲ、センサーをすり抜ける弾：陣営・無敵・「死は一つの状態」を持つダメージ struct と受け手、hit と hurt のレイヤー、スイング id とヒット済みリストを持ちアニメーションのウィンドウで開くクエリ型 hitbox、motor を通したノックバック、毎ステップ cast する弾、データとしての弾幕——2D でも 3D でも |
| | `unity-game-ai` | 壁越しに見つけてくる、決して諦めない、二つの状態の間でちらつく、毎フレーム raycast する敵：予算内の知覚、tick ごとの判断、移動は transform を持つ側に任せる——コードのステートマシン、小さなビヘイビアツリー、視界コーン、聴覚と記憶、巡回と追跡、2D の経路探索、ウェーブスポナー、ターン制の手の評価、そして見てから初めて追うことを証明する journey |
| | `unity-scene-flow` | メニューに戻るとマネージャーが二重になる、90% で止まるロード画面、何も止めないポーズ、壊れたセーブ：決してアンロードされずサービスを持つ Boot シーン、同時に一つしか走らない additive ロード、ポーズも一つの状態であるゲームフェーズのステートマシン、マイグレーションとアトミック書き込みを持つバージョン付きセーブ、作り直されるチェックポイント、オブジェクトプール、ScriptableObject の設定 |
| **バーティカルスライス —— UI** | `unity-game-ui` | **UI の依頼はまずここから。** プロジェクトがどの UI システムを使っているか判定して振り分け、誰も書いていない領域 —— runtime の `OnGUI` HUD —— を自分で受け持ちます |
| | `unity-ui-ugui` | Canvas、RectTransform、Layout Group —— そして uGUI が何も描かなくなる六つの原因 |
| | `unity-ui-toolkit` | UXML/USS、flex、Painter2D —— そして USS が黙って無視するプロパティ |
| **量産 —— アセット** | `unity-3d-models` | 静的なプロップ：AI 生成メッシュのインポート——Unity が目にする前にまず検査し、予算を超えたものだけ減面する |
| | `unity-rigged-character` | 操作できるキャラクター：原画 → image-to-3D → Mixamo → Avatar → Animator → ゲームプレイ用リグ。Mixamo がリグを付けられない体型は、`blender-character-rig` の FBX で置き換える |
| | `unity-2d-sprites` | スプライトシート、スライス、pivot、9-slice、コマ列を再生可能な `AnimationClip` に —— importer の内側にあるメタデータ |
| | `unity-2d-animation` | 2D Animation と PSD Importer パッケージによるスケルタル 2D キャラクター：rig としてインポートする PSB、ボーン・ジオメトリ・ウェイトの順、`SpriteSkin` と CPU または GPU の変形、ランタイムで切り替える Sprite Library のスキンと装備、2D IK、そして rig のコストを示す監査 |
| | `unity-2d-pixel-perfect` | ドット絵がぼける、カメラが動くとピクセルが這う、タイルの継ぎ目に髪の毛のような隙間 —— そして手元にあるのは `PixelPerfectCamera` という名の二つのコンポーネントのどちらなのか |
| | `unity-sprite-atlas` | 同じ draw call に載せたいスプライト：スクリプトからの V2 アトラス、パッキングとプラットフォーム設定、そして焼いたテクスチャがプレイヤーに届くまで |
| | `unity-audio` | メモリ、load type、サンプリングレート、mixer のコスト —— 再インポートの前に必ず報告します |
| | `unity-localization` | 複数言語での出荷と、実際に破綻する CJK フォントのパイプライン |
| **量産 —— AI アセット生成** | `codex-visual` | `codex` の画像モデルで 2D アートを生成し、一冊のアートバイブルと一枚のアンカーでスタイルを固定：グリッド一括生成、短いアニメーションを 1 枚のシートとして生成し計測済みのコマへ切り出して GIF プレビュー、クロマキー透過、サイズ正規化、そして納品ファイルから中心とサイズを読み戻す幾何ゲート |
| | `comfyui-asset-generation` | 自前の ComfyUI で音楽・効果音・MiniMax H3 動画・画像から 3D プロップを生成：一度に一件、`/history` だけを完了の証拠に、モデル切替前に `/free` |
| | `blender-character-rig` | 起動中の Blender を MCP サーバー経由で操作し、画像から生成した 3D キャラクターにリグとアニメーションを付ける：計測したランドマークからボーンを配置、ウェイトは位置から計算、プロップは手のボーンに、アクションをキー入力してプレビューを出し、FBX は再インポートで確かめる |
| **仕上げと最適化** | `unity-game-feel` | 手応えのないヒット、ヒット後に止まったままのゲーム、フラッシュ後に白いままの敵、三十個のピックアップで鳴る三十の音、止まらない振動：ゲームプレイのイベントごとに予算付きのフィードバック行を一つ——`Time.timeScale` の唯一の持ち主によるヒットストップ、元に戻るフラッシュ、ライブラリ不要のスクワッシュと tween、パーティクル、トレイル、発音数上限付きのプール済み SFX、止まる振動 |
| | `unity-render-urp` | 設定したのに出てこないポストプロセス、モバイルで賄える範囲、Render Graph のレビュー |
| | `unity-urp-migration` | Built-in のプロジェクトを五つのゲート付きフェーズで URP へ移す —— 各フェーズは保存済みのプロジェクトから読み直して確認します。途中で止まった移行の診断にも：一面のマゼンタ、PPv2 から Volume への移行、焼き直されないままの lightmap、`GrabPass`／`OnRenderImage` |
| | `unity-profiling` | 遅いフレーム・揺れるフレームの裏で何が動いているのか：Profiler ウィンドウを開かない counter、90 フレーム窓の median/p95/worst、作業量カウンタ、そして前後の比較表 |
| | `unity-scene-optimisation` | プロファイリングの counter がコストを特定したあとに変えるもの：batching の経路と URP で GPU instancing が何もしない理由、`LODGroup` と Mesh LOD、ベイクと GPU の occlusion culling、レイヤーごとのカリング距離、テクスチャサイズと mipmap streaming、sprite とパーティクルの overdraw——どの手段もまず一つの窓で試し、同じ counter で読み戻す |
| | `unity-debug` | 目に見えない変更を検証したいとき —— そして計測結果を信じる前に、計測する側が本当のことを言っていると確かめたいとき |
| **出荷** | `unity-device-testing` | **実機**（Android／iOS）での受け入れテスト：状態が変わるたびにタグ付きの 1 行を出すプローブシーン、そのログに対してアサートしシステムダイアログも押してくれるドライバ、人間には物理操作を 1 回に 1 つだけ頼んで端末側で確認、本当の失敗とハーネスの故障を分ける exit code |
| | `unity-android-release` | ビルドしたあとに**証明する**：成果物を読み返す、keystore と versionCode の規律 |
| | `unity-ios-build` | Xcode を開かずに Unity プロジェクトを iPhone 上のプロセスにする：headless ビルド、署名不要のコンパイルゲート、この Mac が実際に持っているもので署名、`devicectl` でインストール、コンソールが唯一のログ経路、native `.mm` プラグインを 30 秒で反復 |
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
