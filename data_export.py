import os
import json
import requests
import pygsheets
import time
from gql.transport.aiohttp import AIOHTTPTransport
from gql import gql, Client
from google.cloud import storage
from datetime import datetime, timezone, timedelta
import sqlite3

def president2024_realtime():
    bucket = os.environ['BUCKET']
    gc = pygsheets.authorize(service_account_env_var = 'GDRIVE_API_CREDENTIALS')
    url = "https://docs.google.com/spreadsheets/d/1Ar9r7j5LN6eCirNnQ5Lkbl4IEw3UaDQMfdBq5b2oDOE/edit#gid=1764492368"
    sht = gc.open_by_url( url )
    voting_data = { "result": [] }
    try:
        meta_sheet = sht.worksheet_by_title("官網切換相關")
    except Exception as e:
        print("Exception: {}".format(type(e).__name__))
        print("Exception message: {}".format(e))

    voting_data['title'] = meta_sheet.get_value("B2")
    get_cec_data = meta_sheet.get_value("B3")
    switch_view = meta_sheet.get_value("B4")
    cec_data = {}
    readr_data = {}
    tz = timezone(timedelta(hours=+8))
    now = datetime.now(tz)
    date_time = now.strftime("%Y-%m-%d, %H:%M")
    voting_data["updateAt"] = date_time
#    if switch_view == 'T' or get_cec_data == 'T':
    time.sleep(20)
    path = os.path.join(os.environ['ENV_FOLDER'], '2024', 'president', 'map', 'country', 'country.json')
    #if os.path.exists(path):
    #    f = open(path, encoding='utf-8')
    #    cec_data = json.load(f)
    #    print("data from local file")
    #if "summary" not in cec_data:
    cec_json= requests.get('https://whoareyou-gcs.readr.tw/elections/2024/president/map/country/country.json')
    if cec_json.status_code == 200:
        cec_data = json.loads(cec_json.text)

    if cec_data:
        if "updateAt" in cec_data:
            readr_data["updateAt"] = cec_data["updateAt"]
        else:
            readr_data["updateAt"] = date_time
        
        # upload for pure cec data
        readr_data["title"] = "2024 總統大選即時開票"
        if "summary" in cec_data:
            readr_data["result"] = presindent2024_cec( cec_data["summary"], 2 )
            upload_data('whoareyou-gcs.readr.tw', json.dumps(readr_data, ensure_ascii=False).encode('utf8'), 'application/json', "json/2024cec_homepage.json")

    if switch_view == 'T':
        print("Getting the final data")
        voting_data["result"] = presindent2024_cec( cec_data["summary"], 2 )
    else:
        try:
            result_sheet = sht.worksheet_by_title("官網票數")
        except Exception as e:
            print("Exception: {}".format(type(e).__name__))
            print("Exception message: {}".format(e))

        candidates = result_sheet.get_values("B1", "D1")
        sheet_tks = result_sheet.get_values("A2", "D6")
        for row in sheet_tks:
            unit_tks = { "key": row[0], "value": [] }
            for number in range(len(candidates[0])):
                unit_tks['value'].append( { candidates[0][number][0:1]: row[number + 1].replace(",", "") })
                #unit_tks[candidates[0][number]] = row[number]
            voting_data["result"].append(unit_tks)
            
        print("Getting data from sheet")
        if get_cec_data == 'T':
            for result in voting_data["result"]:
                if "key" in result and result["key"] == '鏡新聞':
                    result["value"] = presindent2024_cec( cec_data["summary"] )
            print("Replace the mnews data by cec data")

    upload_data(bucket, json.dumps(voting_data, ensure_ascii=False).encode('utf8'), 'application/json', "json/2024homepage.json")
    return "OK"

def recall202507_realtime():
    gc = pygsheets.authorize(service_account_env_var = 'GDRIVE_API_CREDENTIALS')
    url = "https://docs.google.com/spreadsheets/d/1pri5X5k-_OGxOmRDQ10doKGxs9x4s3ZvU5YJ6D8YmLI/edit"
    sht = gc.open_by_url(url)
    try:
        meta_sheet = sht.worksheet_by_title("官網切換相關")
    except Exception as e:
        print("Exception: {}".format(type(e).__name__))
        print("Exception message: {}".format(e))
        return
    voting_data = { "result": [] }
    voting_data['title'] = meta_sheet.get_value("B2")       
    get_cec_data = meta_sheet.get_value("B3")
    if get_cec_data == 'T':
        cec_json = requests.get('https://whoareyou-gcs.readr.tw/elections-dev/2025_recall_election_data_final/iframe_data.json')
        if cec_json.status_code == 200:
            # 加入 source 欄位
            cec_data = json.loads(cec_json.text)
            cec_data['source'] = 'cec'
            upload_data(
                'whoareyou-gcs.readr.tw',
                json.dumps(cec_data, ensure_ascii=False).encode('utf8'),
                'application/json',
                'json/202507_recall_iframe.json'
            )
            print('Upload 202507_recall_iframe.json successfully')
        else:
            print('Failed to get CEC data:', cec_json.status_code)
    else:
        votePop_local = 'votePop.json'
        votePop_map = {}
        # 只有本地沒有 votePop.json 時才去下載 iframe_data.json 來補
        if not os.path.exists(votePop_local):
            iframe_url = 'https://whoareyou-gcs.readr.tw/elections-dev/2025_recall_election_data_final/iframe_data.json'
            iframe_data = requests.get(iframe_url).json()
            for item in iframe_data['result']:
                votePop_map[item['name']] = item['votePop']
            with open(votePop_local, 'w', encoding='utf-8') as f:
                json.dump(votePop_map, f, ensure_ascii=False, indent=2)
        else:
            with open(votePop_local, 'r', encoding='utf-8') as f:
                votePop_map = json.load(f)
        # 先從 GCS 下載 recall.db
        sqlite_local = 'recall.db'
        download_sqlite_from_gcs('statics-editools-prod', '0726.db', sqlite_local)
        # 查詢 SQLite
        conn = sqlite3.connect(sqlite_local)
        cursor = conn.cursor()
        cursor.execute('SELECT name, agreeTks, disagreeTks, ytpRate, adptVictor FROM A1')
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            name = row[0]
            votePop = votePop_map.get(name, 0)
            disagreeTks = int(row[2])
            ntpRate = round(disagreeTks / votePop * 100, 1) if votePop else 0
            result.append({
                "name": name,
                "votePop": votePop,
                "agreeTks": int(row[1]),
                "disagreeTks": disagreeTks,
                "ytpRate": float(row[3]),
                "adptVictor": row[4],
                "ntpRate": ntpRate
            })
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz)
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "updatedAt": date_time,
            "result": result,
            "source": "mnews"
        }
        json_str = json.dumps(data, ensure_ascii=False)
        upload_data(
            'whoareyou-gcs.readr.tw',
            json_str.encode('utf8'),
            'application/json',
            'json/202507_recall_iframe.json'
        )
        print('Upload recall_iframe.json successfully')

def presindent2024_cec( summary, phase = 1 ):
    tks = []
    tksRate = []
    candVictor = []
    show_victor = False
    if "candidates" not in summary:
        cec_data = [{"key": "得票數", "value": [{"1": 0}, {"2": 0}, {"3": 0}]}, {"key": "得票率", "value": [{"1": 0}, {"2": 0}, {"3": 0}]}]
        return cec_data
    for candidate in summary["candidates"]:
        if candidate["candNo"] < 4:
            tks.append({candidate["candNo"]: candidate["tks"]})
            tksRate.append({candidate["candNo"]: candidate["tksRate"]})
            candVictor.append({candidate["candNo"]: candidate["candVictor"]})
            if candidate["candVictor"]:
                show_victor = True
    if phase == 1:
        final = tks
    else:
        cec_candidates = []
        if show_victor:
            cec_candidates.append({"key": "當選", "value": candVictor})
        cec_candidates.append({"key": "得票數", "value": tks})
        cec_candidates.append({"key": "得票率", "value": tksRate})
        final = cec_candidates
    return final

def sheet2json( url, sheet ):
    gc = pygsheets.authorize(service_account_env_var = 'GDRIVE_API_CREDENTIALS')
    sht = gc.open_by_url( url )

    sheet_titles = sheet.split(',')
    sheets_obj = {}
    for sheet_title in sheet_titles:
        try:
            meta_sheet = sht.worksheet_by_title(sheet_title)
        except Exception as e:
            print("Exception: {}".format(type(e).__name__))
            print("Exception message: {}".format(e))
            continue

        meta_data = meta_sheet.get_all_values()
        #if sheet_name == 'translateurl_for_website':
        #    field_shift = 1
        #else:
        #    field_shift = 0

        field_names = [field_name for field_name in meta_data[0] if field_name != '']
        all_rows = []
        sheet_title_lower = sheet_title.lower()
        if sheet_title_lower in {'pageinfo', 'partners'}:
            all_rows = {}
        
        for i in range(1, len(meta_data)):
            row = meta_data[i]
            if not row[0]:
                break

            values = {field_name:value for field_name, value in zip(field_names[1:], row[1:])}
            if sheet_title_lower == 'pageinfo':
                all_rows[row[0]] = values
            elif sheet_title_lower == 'partners':
                if row[0] in all_rows:
                    all_rows[row[0]].append(values)
                else:
                    all_rows[row[0]] = [values]
            else:
                values = {field_name:value for field_name, value in zip(field_names, row)}
                all_rows.append(values)

        sheets_obj[sheet_title] = all_rows
    return sheets_obj
	

def gql2json(gql_endpoint, gql_string):
    #bucket = os.environ['BUCKET']
    #destination = os.environ('DEST']
    gql_transport = AIOHTTPTransport(url=gql_endpoint)
    gql_client = Client(transport=gql_transport,
                        fetch_schema_from_transport=False)
    # sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

    query = gql(gql_string)
    json_data = gql_client.execute(query)
    #upload_data(bucket, json.dumps(json_data, ensure_ascii=False).encode('utf8'), 'application/json', gcs_path + DEST)
    return json_data

def upload_data(bucket_name: str, data: str, content_type: str, destination_blob_name: str):
    '''Uploads a file to the bucket.'''
    # bucket_name = 'your-bucket-name'
    # data = 'storage-object-content'
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    # blob.content_encoding = 'gzip'
    # try:
    #       data=bytes(data, encoding='utf-8'),
    # except:
    #     print(data)
    blob.upload_from_string(
        # data=gzip.compress(data=data, compresslevel=9),
        #data=bytes(data, encoding='utf-8'),
        data,
        content_type=content_type, client=storage_client)
    blob.content_language = 'zh'
    blob.cache_control = 'max-age=30,public'
    blob.patch()

def download_votePop_from_gcs(bucket_name, blob_name, local_path):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if blob.exists():
        blob.download_to_filename(local_path)
        return True
    return False

def upload_votePop_to_gcs(bucket_name, blob_name, local_path):
    from tools.uploadGCS import upload_blob
    # 將 local_path 上傳到 GCS 的 blob_name 路徑，year 固定為 2025
    upload_blob(local_path, 2025)

def download_sqlite_from_gcs(bucket_name, blob_name, local_path):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)

if __name__ == "__main__":  
    gql_string = """
query { allPosts(where: { tags_every: {name_in: "疫苗"}, state: published }, orderBy: "publishTime_DESC", first: 3) {
    style
    title: name
	slug
    brief
    briefApiData
    contentApiData
    publishTime
    heroImage {
      tiny: urlTinySized
      mobile: urlMobileSized
      tablet: urlTabletSized
      desktop: urlDesktopSized
    } 
    updatedAt
    source
    isAdult
  }
}
"""
    #gql_endpoint = "https://api-dev.example.com"
    #gql2json(gql_endpoint, gql_string)
    keyfile = {
    }
    os.environ['GDRIVE_API_CREDENTIALS'] = json.dumps(keyfile)
    #sheet_content = president2024_realtime("https://docs.google.com/spreadsheets/d/1Ar9r7j5LN6eCirNnQ5Lkbl4IEw3UaDQMfdBq5b2oDOE/edit#gid=1764492368")
    sheet_content = president2024_realtime()
    print(sheet_content)
