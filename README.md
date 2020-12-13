# slack-old-file-delete

Python script, to download and delete old files in slack
指定日時より古いSlack上のファイルを削除します

python 3系で動くと思います。
動作テストは Debian Buster上のpython 3.7で行いました

## 使い方

以下の環境変数をセットします。 (env parameters)

```
SLACK_API_TOKEN=xoxp-xxxxxxxxx...
```

SlackのAPIトークンです。legacy-tokenでテストしています。
発行は以下から。

`https://api.slack.com/custom-integrations/legacy-tokens`

```
SAVE_PATH=c:\save-dir
```
画像ファイルの保存先です。この下にチャンネル名でフォルダが生成され、その中に画像が保存されます。
実行ログもここに出力されるため、DO_DOWNLOAD = Falseでも指定が必要です。

```
MIN_OLD_DAY=30
```
実行日時から何日前より古いファイルを削除するかを指定します。

```
DO_DELETE=True
```
省略可能：デフォルト値 False
削除を実行するか否か(True / False)

```

DO_DOWNLOAD=True
```
省略可能：デフォルト値 False
ファイルのダウンロードを実行するか否か (True / False)

```
EXCLUDE_CHANNELS=G12345678,G98765432
```
省略可能：デフォルト値 なし
処理しないチャンネル。このチャンネルにあるファイルは処理しない。
カンマ区切りで複数チャンネルを指定可能。指定するのはチャンネルIDであることに注意。

## 実行

```
pip3 install -r requirements.txt
python3 slack-old-file-delete.py
```

まず、DO_DELETE=False / DO_DOWNLOAD=False で試しに実行することを強くおすすめします。
また、事故防止の為に py ファイル内に max_loopという変数で最大処理数を制限しています。

実行スクリプトのサンプルは以下。

```
#!/bin/bash

export SLACK_API_TOKEN=xoxp-1234.....

export SAVE_PATH=/work/slack-save
export MIN_OLD_DAY=21
export DO_DELETE=False
export DO_DOWNLOAD=True

# 処理除外チャンネル。カンマ区切り
export EXCLUDE_CHANNELS=GABCDEEF

mkdir -p $SAVE_PATH
cd ~/scripts/slack-old-file-delete
python3 slack-old-file-delete.py
```

## changelog

### v1.50

* 多数のバグ修正

### v1.20

* 初期バージョン