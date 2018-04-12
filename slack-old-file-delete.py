import logging
from slackclient import SlackClient
from datetime import datetime
from datetime import timedelta
from time import sleep
import os

# CONFIG ######################################################################################
save_dir = os.environ["SAVE_PATH"]  # 'c:\\save-dir'

slack_token = os.environ["SLACK_API_TOKEN"]
delete_delta = timedelta(days=int(os.environ["MIN_OLD_DAY"]))

do_delete = os.environ["DO_DELETE"]    # Falseにすると削除は行わない
do_download = os.environ["DO_DOWNLOAD"]   # Falseにするとダウンロードしない

file_type = "images" # slackファイルタイプ

log_filename = "slack-old-file-delete.log"
log_format = '%(asctime)s %(name)s %(levelname)s %(message)s'

#元ファイル名から最大何文字まで取るか。max:save_dir文字数 - 250程度(windows)
max_filename_len = 150

# 最大ループ数。 この数 * 30ファイルを処理したら停止
max_loop = 50

# CONFIG ######################################################################################

def fetch_channel_list():
    # チャンネル一覧（名前がほしい）
    channels_response = sc.api_call(
        "channels.list",
    )

    if channels_response['ok'] != True:
        raise ApiFailError

    return channels_response

def fetch_group_list():
    # グループ名一覧（グループDM・プライベートチャンネルの名前がほしい）
    groups_response = sc.api_call(
        "groups.list",
    )

    if groups_response['ok'] != True:
        raise ApiFailError

    return groups_response

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

def get_group_name(id):
    """
    プライベートグループ・グループDMの名前取得
    見つからなかった場合 None
    """
    for group in groups_response['groups']:
        if group['id'] == id:
            return group['name']


    logger.warning("private group or group dm name not found (maybe not accessible)-> " + id)
    return None

def download_file(url, savepath):
    import requests
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

    return True

def create_download_filename(file_info):
    """
    save_dir + yyyymmddhhmmss_id_originalname
    import os
    """

    # memo created はJSTで返してきてる
    datestr = datetime.fromtimestamp(file_info['created']).strftime('%Y%m%d%H%M%S')

    channel_name = None

    # ファイルは複数チャンネルに属することができるが先頭のチャンネルに保存
    # プライベートチャンネルの場合は、 channels[0] が存在しないので例外
    if len(file_info['channels']) != 0:
        channel_id = file_info['channels'][0]
        channel_name = get_channel_name(channel_id)
    elif len(file_info['groups']) != 0:
        # private channelはグループDMと同一扱い
        channel_id = file_info['groups'][0]
        channel_name = get_group_name(channel_id)
    else:
		# 諦めて適当な名前をつける
        channel_name = "_孤立ファイル"

    if channel_name == None:
        logger.error("can't get name ID=" + file_info['id'])
        return None # Noneを返すとskipする

    # memo slackの表示上は title が表示されるがファイル名的に不適切な文字があるので permalinkから拾う
    org_file_name = get_filename_from_url(file_info['permalink'])

    # ファイル名が長すぎると保存できないので、切る
    if len(org_file_name) > max_filename_len:
        file_name_split = os.path.splitext(org_file_name)
        file_name = file_name_split[0][0:max_filename_len] + file_name_split[1]
        logger.warn("filename truncated " + org_file_name + " -> " + file_name)
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
        file = file_id
    )

    if response['ok'] != True:
        raise Exception("delete file failed id->" + file_id)

    logger.info("deleted remote file ID=" + file_id)
    return True

def get_file_list(max_timestamp):
    #ファイル一覧
    files_response = sc.api_call(
        "files.list",
        count=30,
        types=file_type,
        ts_to = max_timestamp
    )

    if files_response['ok'] != True:
        raise ApiFailError

    return files_response

def timestamp_to_str(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y/%m/%d %H:%M:%S')

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

	logger.info("** START")
    logger.info("DO_DOWNLOAD = " + str(do_download) + " DO_DELETE = " + str(do_delete))

	# main
	sc = SlackClient(slack_token)

	max_date = datetime.now() - delete_delta
	print("max_date = " + str(max_date))
	max_timestamp = max_date.timestamp()

	channels_response = fetch_channel_list()
	groups_response = fetch_group_list()

	# main loop
	max_ts = max_timestamp
	file_count = 1

	logger.info("process start. start max_ts=" + str(max_ts) + " " + timestamp_to_str(max_ts))
	for i in range(max_loop):
		logger.info("#### loop " + str(i + 1) + " of " + str(max_loop))

		file_list = get_file_list(max_ts)
		logger.info("request filelist max_ts=" + str(max_ts) + " ("
					+ timestamp_to_str(max_ts) + ") #####")

		if len(file_list['files']) == 0:
			logger.info("file list is empty. complete.")
			break

		for file in file_list['files']:
			p = create_download_filename(file)
			logger.info("COUNT=" + str(file_count) + " ID=" + file['id'] + " created=" + str(file['created'])
						+ " (" + datetime.fromtimestamp(file['created']).strftime('%Y/%m/%d %H:%M:%S')
						+ ") TITLE=" + file['title'] + " " + file['url_private'] + " " + str(p))

			if p != None:
				download_file(file['url_private'], p)
				delete_remote_file(file['id'])
			else:
				logger.warning("skipped private group or group dm file." + file['id'])

			# 次のリクエスト用
			max_ts = file['created'] - 1   # 同一ファイルがひっかかるのを防止
			file_count = file_count + 1
			sleep(1)

	logger.info("process end. end max_ts=" + str(max_ts) + " " + timestamp_to_str(max_ts))
	logger.info("** END")
