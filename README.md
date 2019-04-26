# trace_model_replace

## 機能概要

vmd(MMDモーションデータ)を、指定されたモデルに適用したサイズで再生成します。


## 準備

詳細は、ニコニコ動画(準備中)を参照して下さい。

### 依存関係

python3系 で以下をインストールして下さい

- numpy
- PyQt5

## 実行方法

1. [ReplaceTraceModel.bat](ReplaceTraceModel.bat) を実行する
1. `入力vmdファイルパス` が聞かれるので、調整したいVMDファイルパスを指定する
1. `トレース元モデルボーン構造CSVファイル` が聞かれるので、トレース元となったモデルのボーン構造CSVファイルパスを指定する
    - ボーン構造CSVファイルの出力方法は、VMD-3d-pose-baseline-multiの[born/README.md](https://github.com/miu200521358/VMD-3d-pose-baseline-multi/tree/master/born/README.md)参照
    - 未指定の場合、デフォルトで[born/あにまさ式ミク準標準.csv](born/あにまさ式ミク準標準.csv)が読み込まれる
1. `トレース変換先モデルボーン構造CSVファイル` が聞かれるので、変換したいモデルのボーン構造CSVファイルパスを指定する
    - 未指定の場合、デフォルトで[born/あにまさ式ミク準標準.csv](born/あにまさ式ミク準標準.csv)が読み込まれる
1. `詳細なログを出すか` 聞かれるので、出す場合、`yes` を入力する
    - 未指定 もしくは `no` の場合、通常ログ
1. 処理開始
1. 処理が終了すると、`vmd`サブディレクトリに変換したVMDデータが出力される
	- {入力vmdファイル名}_{トレース変換先モデル名}_{日時}.vmd
1. MMDを起動し、モデルを読み込んだ後、モーションを読み込む

## 任意事項

生成したモーションに関して、以下の行為は自由に行って下さい

 - モーションの調整・改変
 - ニコニコ動画、Youtube、Twitter等へのモーション使用動画投稿
   - 進捗等で生成したモーションそのままを投稿することも問題ありません。

**※不特定多数に対する配布は、元々のモーションを作成された作者様にご確認ください。**

## 禁止事項
生成したモーションに関して、以下の行為はご遠慮願います

 - 自動生成したモーションのまま不特定多数に配布する行為
 - モーションの完全自作発言
 - 各権利者様のご迷惑になるような行為
 - 営利目的の利用
 - 他者の誹謗中傷目的の利用（二次元・三次元不問）
 - 過度な暴力・猥褻・恋愛・猟奇的・政治的・宗教的表現を含む（R-15相当）作品への利用
 - その他、公序良俗に反する作品への利用

## 免責事項
 - 自己責任でご利用ください
 - キット使用によって生じたいかなる問題に関して、作者は一切の責任を負いかねます

## ライセンス
Apache License 2.0

 - 変換したVMDモーションの結果を公開・配布する場合は、必ずライセンスの明記をお願い致します。
 - ニコニコ動画の場合、コンテンツツリーへ配布動画(準備中)を登録してください。

```
ツール名：VMDサイジング
作者：miu200521358
```

## 連絡先
 - Twitter：https://twitter.com/miu200521358
 - メール：garnet200521358@gmail.com
