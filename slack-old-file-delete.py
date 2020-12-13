import logging
from slack import WebClient
from datetime import datetime
from datetime import timedelta
from time import sleep
import requests

import os

def parse_boolstr(boolstr):
    if boolstr.lower() == "true" or boolstr.lower() == "1":
        return True
    else:
        return False

# CONFIG ######################################################################################
save_dir = os.environ["SAVE_PATH"]  # 'c:\\save-dir'

slack_token = os.environ["SLACK_API_TOKEN"]
delete_delta = timedelta(days=int(os.environ["MIN_OLD_DAY"]))

do_delete = parse_boolstr(os.getenv("DO_DELETE", 'True'))       # Falseにすると削除は行わない
do_download = parse_boolstr(os.getenv("DO_DOWNLOAD", 'False'))   # Falseにするとダウンロードしない

exclude_channels = os.getenv("EXCLUDE_CHANNELS","").split(",")

file_type = "images" # slackファイルタイプ

log_filename = "slack-old-file-delete.log"
log_format = '%(asctime)s %(name)s %(levelname)s %(message)s'

#パスの最大長。 Windowsなら 250程度
max_path_len = 230

# 最大ループ数。 この数 * 30ファイルを処理したら停止
max_loop = 50

# DANGERZONE
process_private = False   # プライベートグループ、DMのファイルを処理するか

version = "1.50"

# CONFIG ######################################################################################

def fetch_channel_list():
    """
    チャンネル、DM、マルチDM一覧取得
    """
    # channels_response = sc.api_call(
    #     api_method="channels.list",
    #     json={'exclude_members': True}
    # )
    channels_response = sc.conversations_list(
        types="public_channel, private_channel, mpim, im",
        limit=1000       
    )

    if channels_response['ok'] != True:
        raise ApiFailError

    return channels_response


def get_channel_name(id):
    """
    パブリックチャンネルの名前取得
    見つからなかった場合 None
    """
    for channel in channels_response['channels']:
        if channel['id'] == id:
            return channel['name']

    logger.warning("channel name not found (maybe not accessible)-> " + id)
    return None

def download_file(url, savepath):
    import struct

    if do_download != True:
        return False

    path = os.path.dirname(savepath)
    os.makedirs(path) if os.path.exists(path) == False else None

    headers = {'Authorization': 'Bearer ' + slack_token}
    response = requests.get(url, headers=headers)

    with open(savepath, "wb") as fout:
        for x in response.content:
            fout.write(struct.pack("B", x))

    logger.info("download remote file. localpath=" + savepath)
    return True

def get_chat_name(file_info):
    """
    チャンネル名、グループDM、プライベートチャンネルの名前を取得する
    ファイルは複数チャンネルに属することができるが先頭のチャンネル名を返す
    """
    if len(file_info['channels']) != 0:
        channel_id = file_info['channels'][0]
        channel_name = get_channel_name(channel_id)
    elif len(file_info['groups']) != 0:
        # private channelはグループDMと同一扱い
        channel_id = file_info['groups'][0]
        channel_name = "PRIVATE_" + get_channel_name(channel_id)
    else:
        # 諦めて適当な名前をつける
        channel_name = "_孤立ファイル"

    return channel_name

def is_exclude_channels(file_info):
    groups = file_info['channels'] + file_info['groups']
    for group in groups:
        if group in exclude_channels:
            return True

    return False

def create_download_filename(file_info):
    """
    save_dir + yyyymmddhhmmss_id_originalname
    処理してはいけないファイルの場合 None がかえる
    """

    # memo created はJSTで返してきてる
    datestr = datetime.fromtimestamp(file_info['created']).strftime('%Y%m%d%H%M%S')

    channel_name = get_chat_name(file_info)

    if channel_name == None:
        logger.error("[SKIP] can't get channel name. ID=" + file_info['id'])
        return None # Noneを返すとskipする

    if len(file_info['groups']) != 0 and not process_private:
        logger.info("[SKIP] private file. " + channel_name + " " + file_info['id'])
        return None

    if is_exclude_channels(file_info):
        logger.info("[SKIP] exclude channel. " + channel_name + " " + file_info['id'])
        return None

    # memo slackの表示上は title が表示されるがファイル名的に不適切な文字があるので permalinkから拾う
    org_file_name = get_filename_from_url(file_info['permalink'])

    # ファイル名に使ってよい長さを求める
    used_len = len(os.path.join(save_dir, channel_name))
    filename_max_len = max_path_len - used_len

    # ファイル名が長すぎると保存できないので、切る
    if len(org_file_name) > filename_max_len:
        file_name_split = os.path.splitext(org_file_name)

        filename_base_max_len = filename_max_len - len(file_name_split[1])  # 拡張子分引く

        file_name = file_name_split[0][0:filename_base_max_len] + file_name_split[1]
        logger.debug("filename truncated " + org_file_name + " -> " + file_name)
    else:
        file_name = org_file_name

    path = os.path.join(save_dir, channel_name, datestr + "-" + file_info['id'] + "-" + file_name)

    return path

def get_filename_from_url(url):
    return url.rsplit("/", 1)[1]

def delete_remote_file(file_id):
    if do_delete != True:
        return False

    response = sc.api_call(
        "files.delete",
        json={'file': file_id}
    )

    if response['ok'] != True:
        raise Exception("delete file failed id->" + file_id)

    logger.info("deleted remote file ID=" + file_id)
    return True

def get_file_list(max_timestamp):
    """
    ファイル一覧の取得
    """
    # files.list APIは call_apiで呼ぶことが出来ない（呼べるが、パラメタを渡せない）

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    params = {'token': slack_token, 'count': 200, 'types': file_type, 'ts_to': max_timestamp}

    response = requests.post('https://slack.com/api/files.list',
                        headers=headers,
                        params=params)

    files_response = response.json()

    if files_response['ok'] != True:
        logger.error(files_response)
        raise ApiFailError

    return files_response

def timestamp_to_str(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y/%m/%d %H:%M:%S')

############################################################################################
# MAIN
############################################################################################
if __name__ == '__main__':
    # logging
    log_path = os.path.join(save_dir, log_filename)

    logger = logging.getLogger('main')
    logger.setLevel(10)
    logger.format=log_format

    file_handler = logging.FileHandler(log_path, encoding='UTF8')
    file_handler.setFormatter(logging.Formatter(log_format))

    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(log_format))

    logger.addHandler(file_handler)
    logger.addHandler(stdout_handler)

    logger.info("** START " + str(version))
    logger.info("DO_DOWNLOAD = " + str(do_download) + " DO_DELETE = " + str(do_delete))
    logger.info("exclude_channels " + str(exclude_channels))

    # main
    #sc = SlackClient(slack_token)
    sc = WebClient(token=slack_token)

    max_date = datetime.now() - delete_delta
    max_timestamp = int(max_date.timestamp())
    if (do_delete):
        logger.info("Delete files before " + timestamp_to_str(max_timestamp))
    else:
        logger.info("Disable file deletion.")

    channels_response = fetch_channel_list()

    # main loop
    max_ts = max_timestamp
    file_count = 1

    logger.info("process start. start max_ts=" + str(max_ts) + " " + timestamp_to_str(max_ts))
    for i in range(max_loop):
        file_list = get_file_list(max_ts)
        sleep(2)  # 過負荷防止用sleep
        logger.info(f"Requested filelist #{i + 1}/{max_loop}" 
                    + f" max_ts(until this timestamp)={max_ts}"
                    + f" ({timestamp_to_str(max_ts)})"
                    + f" file count = {len(file_list['files'])}")

        if len(file_list['files']) == 0:
            logger.info("File list is empty. complete.")
            break

        for file in file_list['files']:
            p = create_download_filename(file)
            file_date = datetime.fromtimestamp(file['created'])

            if file_date < max_date and p != None:
                logger.info(f"Delete file ID={file['id']}" 
                            + f" created={file['created']}"
                            + f" ({file_date.strftime('%Y/%m/%d %H:%M:%S')})"
                            + f" TITLE=file['title']"
                            + f" {file['url_private']} {p}")

                download_file(file['url_private'], p)
                delete_remote_file(file['id'])
                sleep(1)  # 過負荷防止用sleep
            else:
                #logger.debug("skipped. id=" + file['id'])
                pass

            # 次のリクエスト用
            file_count = file_count + 1
            if file['created'] < max_ts:
                max_ts = int(file['created'] - 1)   # 同一ファイルがひっかかるのを防止
                logger.debug(f"max_ts updated {max_ts}")

        logger.info(f"Files processed {file_count}")

    logger.info("process end. end max_ts=" + str(max_ts) + " " + timestamp_to_str(max_ts))
    logger.info("** END")
