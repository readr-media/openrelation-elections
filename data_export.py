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
from tools.cec_data import request_cec

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
    base_bucket_folder =  os.getenv('BASE_BUCKET_FOLDER_202507', 'elections-dev')
    gc = pygsheets.authorize(service_account_env_var = 'GDRIVE_API_CREDENTIALS')
    url = "https://docs.google.com/spreadsheets/d/1pri5X5k-_OGxOmRDQ10doKGxs9x4s3ZvU5YJ6D8YmLI/edit"
    sht = gc.open_by_url(url)
    try:
        meta_sheet = sht.worksheet_by_title("官網切換相關")
    except Exception as e:
        print("Exception: {}".format(type(e).__name__))
        print("Exception message: {}".format(e))
        return
    
    # 新增：取得 homepage_display sheet 並轉為 json，上傳到 GCS
    try:
        homepage_display_sheet = sht.worksheet_by_title("homepage_display")
        homepage_display_data = homepage_display_sheet.get_all_values()
        # 轉為 json 格式
        if homepage_display_data:
            homepage_display_json = {}
            for row in homepage_display_data[1:]:
                if not row or not row[0]:
                    break
                key = row[0]
                value = row[1]
                homepage_display_json[key] = value
            upload_data(
                'whoareyou-gcs.readr.tw',
                json.dumps(homepage_display_json, ensure_ascii=False).encode('utf8'),
                'application/json',
                'json/202507_recall_homepage_display.json'
            )
            print('Upload 202507_recall_homepage_display.json successfully')
    except Exception as e:
        print("Exception: {}".format(type(e).__name__))
        print("Exception message: {}".format(e))
    voting_data = { "result": [] }
    #voting_data['title'] = meta_sheet.get_value("B2")       
    get_cec_data = meta_sheet.get_value("B2")
    print("source = " + get_cec_data)
    display_iframe = meta_sheet.get_value("B3")  # 讀取 display_iframe
    if get_cec_data == 'T':
        cec_json = requests.get(f'https://whoareyou-gcs.readr.tw/{base_bucket_folder}/2025/legislator/iframe/recall-july/iframe.json')
        if cec_json.status_code == 200:
            # 加入 source 欄位
            cec_data = json.loads(cec_json.text)
            cec_data['source'] = 'cec'
            cec_data['display_iframe'] = display_iframe  # 加入 display_iframe
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
        # 先從 GCS 下載 recall.db
        sqlite_local = 'recall.db'
        download_sqlite_from_gcs('statics-editools-prod', '0726.db', sqlite_local)
        # 查詢 SQLite
        conn = sqlite3.connect(sqlite_local)
        cursor = conn.cursor()
        cursor.execute('SELECT name, agreeTks, disagreeTks, ytpRate, adptVictor, gmeb FROM A1')
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            name = row[0]
            votePop = int(row[5]) if row[5] else 0  # gmeb 欄位
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
            "source": "mnews",
            "display_iframe": display_iframe  # 加入 display_iframe
        }
        json_str = json.dumps(data, ensure_ascii=False)
        upload_data(
            'whoareyou-gcs.readr.tw',
            json_str.encode('utf8'),
            'application/json',
            'json/202507_recall_iframe.json'
        )
        print('Upload recall_iframe.json successfully')

def load_recall_mapping():
    base_bucket_folder =  os.getenv('BASE_BUCKET_FOLDER_202507', 'elections-dev')
    recallno_mapping_json = requests.get(f'https://whoareyou-gcs.readr.tw/{base_bucket_folder}/candNo-mapping/202507_recallno_mapping.json')
    return recallno_mapping_json.json()

def get_templates(base_url, recall_mapping):
    def fetch_constituency():
        for country, areas in recall_mapping.items():
            for item in areas:
                area = item['area']
                if area == 'NA':
                    continue
                constituency = f'{country}{area}'
                url = base_url.format('constituency', constituency)
                yield country, area, requests.get(url).json()
    def fetch_country():
        url = base_url.format('country', 'country')
        return 'country', requests.get(url).json()
    def fetch_county():
        for county in recall_mapping.keys():
            url = base_url.format('county', county)
            yield county, requests.get(url).json()
    return list(fetch_constituency()), fetch_country(), list(fetch_county())

def parse_202507_constituency_data(template, cec_data):
    districts = []
    for district in template['districts']:
        deptCode = district['town']
        villcode = district['vill']
        data = None if cec_data is None or deptCode not in cec_data or villcode not in cec_data[deptCode] else cec_data[deptCode][villcode]
        district_data = {
            'range': district['range'],
            'area_nickname': district['area_nickname'],
            'county': district['county'],
            'area': district['area'],
            'town': district['town'],
            'vill': district['vill'],
            'type': district['type'],
            'profRate': 0.0 if data is None else data['profRate'],
            'votePop': 0 if data is None else data['gmeb'],
            'candidates': [
                {
                    'candNo': candidate['candNo'],
                    'name': candidate['name'],
                    'party': candidate['party'],
                    'agreeTks': 0 if data is None else data['agreeTks'],
                    'disagreeTks': 0 if data is None else data['disagreeTks'],
                    'agreeRate': 0.0 if data is None else data['agreeRate'],
                    'disagreeRate': 0.0 if data is None else data['disagreeRate'],
                    'adptVictor': '' if data is None else data['adptVictor'],
                    'ytpRate': 0.0 if data is None else data['ytpRate'],
                    'ntpRate': 0.0 if data is None else round(data['disagreeTks'] / data['gmeb'] * 100, 2)
                }
                for candidate in district['candidates']
            ]
        }
        districts.append(district_data)
    return districts

def format_202507_timestamp(timestamp_str):
    if not timestamp_str or len(timestamp_str) != 10:
        return "2025-07-03 20:15:00"
    
    month = timestamp_str[:2]
    day = timestamp_str[2:4] 
    hour = timestamp_str[4:6]
    minute = timestamp_str[6:8]
    second = timestamp_str[8:10]
    
    return f"2025-{month}-{day} {hour}:{minute}:{second}"

def find_candidate_no(recall_mapping, constituency_code, area_code):
    candidate = 'A01'
    
    if constituency_code in recall_mapping:
        for item in recall_mapping[constituency_code]:
            if item['area'] == area_code:
                candidate = item['no']
                break
    
    return candidate

def transform_cec_data_with_tbox_no(cec_data, candidate, voter_mapping=None, county_code=None):
    if cec_data is None:
        return None
    
    if voter_mapping is None:
        voter_mapping = json.load(open('./mapping/2025/voter.json', 'r', encoding='utf-8'))
    
    data = {}
    for vill_status in cec_data[candidate]:
        dept_code = vill_status['deptCode']
        tbox_no = str(vill_status['tboxNo']).zfill(4)
        
        if dept_code not in data:
            data[dept_code] = {}
        
        mapping_key = f"{county_code}{dept_code}" if county_code else dept_code
        
        villcode = tbox_no
        if mapping_key in voter_mapping and tbox_no in voter_mapping[mapping_key]:
            villcode = voter_mapping[mapping_key][tbox_no]['villcode']
        
        if villcode in data[dept_code]:
            existing = data[dept_code][villcode]
            existing['agreeTks'] += vill_status.get('agreeTks', 0)
            existing['disagreeTks'] += vill_status.get('disagreeTks', 0)
            existing['gmeb'] += vill_status.get('gmeb', 0)
            existing['prof3'] += vill_status.get('prof3', 0)
            total_votes = existing['agreeTks'] + existing['disagreeTks']
            if total_votes > 0:
                existing['agreeRate'] = round(existing['agreeTks'] / total_votes * 100, 2)
                existing['disagreeRate'] = round(existing['disagreeTks'] / total_votes * 100, 2)
            if existing['gmeb'] > 0:
                existing['profRate'] = round(existing['prof3'] / existing['gmeb'] * 100, 2)
                existing['ytpRate'] = round(total_votes / existing['gmeb'] * 100, 2)
            for key in vill_status:
                if key not in ['agreeTks', 'disagreeTks', 'gmeb', 'prof3', 'agreeRate', 'disagreeRate', 'profRate', 'ytpRate']:
                    existing[key] = vill_status[key]
        else:
            data[dept_code][villcode] = vill_status
    
    return data

def find_candidate_vote_data(candidate_votes):
        for candidate_vote in candidate_votes:
            if candidate_vote['deptCode'] == '000':
                return candidate_vote
        return None

def extract_candidate_vote_info(candidate_vote):
    return {
        "agreeTks": candidate_vote['agreeTks'],
        "disagreeTks": candidate_vote['disagreeTks'],
        "agreeRate": candidate_vote['agreeRate'],
        "disagreeRate": candidate_vote['disagreeRate'],
        "adptVictor": candidate_vote['adptVictor'],
        "ytpRate": candidate_vote['ytpRate'],
        "ntpRate": round(candidate_vote['disagreeTks'] / candidate_vote['gmeb'] * 100, 2)
    }

def calculate_statistics_by_country(cec_data, recall_mapping):
    gmeb_data = {}
    prof_count_data = {}
    candidate_data = []
    
    if cec_data is None:
        return gmeb_data, prof_count_data, candidate_data
    
    for country, areas in recall_mapping.items():
        gmeb_data[country] = 0
        prof_count_data[country] = 0
        
        for item in areas:
            area = item['area']
            candidate = item['no']
            
            if area == 'NA':
                continue

            candidate_vote = find_candidate_vote_data(cec_data[candidate])
            if candidate_vote:
                gmeb_data[country] += candidate_vote['gmeb']
                prof_count_data[country] += candidate_vote['prof3']
                candidate_data.append(extract_candidate_vote_info(candidate_vote))
    
    return gmeb_data, prof_count_data, candidate_data

def calculate_prof_rate(prof_count_data, gmeb_data):
    total_prof_count = sum(prof_count_data.values())
    total_gmeb = sum(gmeb_data.values())
    
    if total_gmeb == 0:
        return 0.0
    
    return round(total_prof_count / total_gmeb * 100, 2)

def update_candidate_info(candidates, candidate_data, cec_data):
    for i, candidate in enumerate(candidates):
        if cec_data is None:
            set_default_candidate_values(candidate)
        else:
            if i < len(candidate_data):
                update_candidate_with_data(candidate, candidate_data[i])
            else:
                set_default_candidate_values(candidate)

def set_default_candidate_values(candidate):
    candidate.update({
        'agreeTks': 0,
        'disagreeTks': 0,
        'agreeRate': 0.0,
        'disagreeRate': 0.0,
        'adptVictor': '',
        'ytpRate': 0.0,
        'ntpRate': 0.0
    })

def update_candidate_with_data(candidate, candidate_vote_data):
    candidate.update({
        'agreeTks': candidate_vote_data['agreeTks'],
        'disagreeTks': candidate_vote_data['disagreeTks'],
        'agreeRate': candidate_vote_data['agreeRate'],
        'disagreeRate': candidate_vote_data['disagreeRate'],
        'adptVictor': candidate_vote_data['adptVictor'],
        'ytpRate': candidate_vote_data['ytpRate'],
        'ntpRate': candidate_vote_data['ntpRate']
    })

def update_summary_data(country_data_summary, candidate_data, cec_data, prof_count_data, gmeb_data):
    country_data_summary['profRate'] = 0.0 if cec_data is None else calculate_prof_rate(prof_count_data, gmeb_data)
    update_candidate_info(country_data_summary['candidates'], candidate_data, cec_data)

def update_districts_data(country_data_districts, candidate_data, cec_data, prof_count_data, gmeb_data):
    for district in country_data_districts:
        county = district['county']
        prof_count = prof_count_data.get(county, 0)
        gmeb = gmeb_data.get(county, 0)
        
        district['profRate'] = 0.0 if cec_data is None else (round(prof_count / gmeb * 100, 2) if gmeb > 0 else 0.0)
        
        update_candidate_info(district['candidates'], candidate_data, cec_data)

def update_districts_data_by_summary(summary_data, districts_data):
    for district in districts_data:
        for candidate in district['candidates']:
            for summary_candidate in summary_data['candidates']:
                if candidate['name'] == summary_candidate['name']:
                    update_candidate_with_data(candidate, summary_candidate)
                    break

def get_updated_at(country_data, cec_data):
    if cec_data is None:
        return country_data['updatedAt']
    else:
        return format_202507_timestamp(cec_data['ST'])

def process_constituency_data(bucket_name, filename, constituencies, recall_mapping, is_started, is_running, final_data):
    voter_mapping = json.load(open('./mapping/2025/voter.json', 'r', encoding='utf-8'))
    
    for constituency in constituencies:
        cec_data = final_data if is_started & (not is_running) else None
        updatedAt = constituency[2]['updatedAt'] if cec_data is None else format_202507_timestamp(cec_data['ST'])
        county_code = constituency[0]
        cec_data = transform_cec_data_with_tbox_no(cec_data, find_candidate_no(recall_mapping, constituency[0], constituency[1]), voter_mapping, county_code)
        districts = parse_202507_constituency_data(constituency[2], cec_data)
        data = {
            'updatedAt': updatedAt,
            'is_running': is_running,
            'is_started': is_started,
            'districts': districts
        }
        dump_2025_recall_data(bucket_name, filename.format(constituency[0] + constituency[1]), data)

def process_country_data(bucket_name, filename, countries, recall_mapping, is_started, is_running, running_data, final_data):
    country_data = countries[1]
    country_data_summary = country_data['summary']
    country_data_districts = country_data['districts']
    
    cec_data = None if not is_started else running_data if is_running else final_data
    
    gmeb_data, prof_count_data, candidate_data = calculate_statistics_by_country(cec_data, recall_mapping)
    
    update_summary_data(country_data_summary, candidate_data, cec_data, prof_count_data, gmeb_data)
    
    update_districts_data_by_summary(country_data_summary, country_data_districts)
    #update_districts_data(country_data_districts, candidate_data, cec_data, prof_count_data, gmeb_data)
    
    data = {
        'updatedAt': get_updated_at(country_data, cec_data),
        'is_running': is_running,
        'is_started': is_started,
        'summary': country_data_summary,
        'districts': country_data_districts
    }
    
    dump_2025_recall_data(bucket_name, filename, data)

    return data

def process_county_data(bucket_name, filename, counties, recall_mapping, is_started, is_running, running_data, final_data):
    cec_data = None if not is_started else running_data if is_running else final_data
    for county, county_data in counties:
        updatedAt = county_data['updatedAt'] if cec_data is None else format_202507_timestamp(cec_data['ST'])
        districts = county_data['districts']
        for district in districts:
            total_vote_pop = 0
            total_prof_count = 0
            for candidate in district['candidates']:
                if cec_data is None:
                    set_default_candidate_values(candidate)
                else:
                    candidate_vote = find_candidate_vote_data(cec_data[find_candidate_no(recall_mapping, county, district['area'])])
                    if candidate_vote is None:
                        set_default_candidate_values(candidate)
                    else:
                        total_vote_pop += candidate_vote['gmeb']
                        total_prof_count += candidate_vote['prof3']
                        candidate_vote['ntpRate'] = round(candidate_vote['disagreeTks'] / candidate_vote['gmeb'] * 100, 2) 
                        update_candidate_with_data(candidate, candidate_vote)
            district['votePop'] = total_vote_pop
            district['profRate'] = round(total_prof_count / total_vote_pop * 100, 2) if total_vote_pop > 0 else 0.0
        data = {
            'updatedAt': updatedAt,
            'is_running': is_running,
            'is_started': is_started,
            'districts': districts
        }

        dump_2025_recall_data(bucket_name, filename.format(county), data)

def process_iframe(base_bucket_folder, bucket_name, filename, countries, recall_mapping, is_started, is_running, running_data, final_data):
    cec_data = None if not is_started else running_data if is_running else final_data
    country_data = countries[1]
    
    base_url = f'https://whoareyou-gcs.readr.tw/{base_bucket_folder}' + '/2025/legislator/map/{}/recall-july/{}.json'
    constituencies, _, _ = get_templates(base_url, recall_mapping)
    
    candidate_no_to_name = {}
    
    for county_code, area_code, constituency_data in constituencies:
        if constituency_data.get('districts') and constituency_data['districts']:
            district = constituency_data['districts'][0]
            if district.get('candidates'):
                candidate_name = district['candidates'][0]['name']
                for areas in recall_mapping.get(county_code, []):
                    if areas['area'] == area_code:
                        candidate_no = areas['no']
                        candidate_no_to_name[candidate_no] = candidate_name
                        break
    
    candidate_no_to_name['A25'] = '高虹安'
    
    all_candidates = set()
    for areas in recall_mapping.values():
        for item in areas:
            candidate_no = item.get('no')
            if candidate_no:
                all_candidates.add(candidate_no)
    
    result = []
    
    for candidate_no in sorted(all_candidates):
        candidate_name = candidate_no_to_name.get(candidate_no, f'候選人{candidate_no}')
        
        candidate_vote = None
        if cec_data and candidate_no in cec_data:
            candidate_vote = find_candidate_vote_data(cec_data[candidate_no])
        
        if candidate_vote:
            result.append({
                'name': candidate_name,
                'votePop': candidate_vote.get('gmeb', 0),
                'agreeTks': candidate_vote['agreeTks'],
                'disagreeTks': candidate_vote['disagreeTks'],
                'ytpRate': candidate_vote['ytpRate'],
                'ntpRate': round(candidate_vote['disagreeTks'] / candidate_vote['gmeb'] * 100, 2) if candidate_vote['gmeb'] > 0 else 0.0,
                'adptVictor': candidate_vote.get('adptVictor', '')
            })
        else:
            result.append({
                'name': candidate_name,
                'votePop': 0,
                'agreeTks': 0,
                'disagreeTks': 0,
                'ytpRate': 0.0,
                'ntpRate': 0.0,
                'adptVictor': ''
            })
    
    data = {
        'updatedAt': get_updated_at(country_data, cec_data),
        'result': result
    }
    
    dump_2025_recall_data(bucket_name, filename, data)

def process_mobile(base_bucket_folder, bucket_name, filename, is_started, is_running, country_data):
    district_files = [
        'changhuaCounty', 'chiayiCity', 'chiayiCounty', 
        'hsinchuCity', 'hsinchuCounty', 'hualienCounty',
        'kaohsiungCity', 'keelungCity', 'kinmenCounty',
        'lienchiangCounty', 'miaoliCounty', 'nantouCounty',
        'newTaipeiCity', 'penghuCounty', 'pingtungCounty',
        'taichungCity', 'tainanCity', 'taipeiCity',
        'taitungCounty', 'taoyuanCity', 'yilanCounty', 
        'yunlinCounty'
    ]

    base_url = f'https://whoareyou-gcs.readr.tw/{base_bucket_folder}' + '/v2/2025/recall/district/{}.json'
    for district_file in district_files:
        request_data = requests.get(base_url.format(district_file))
        if request_data.status_code == 200:
            district_data = request_data.json()
            district_data['updatedAt'] = country_data['updatedAt']
            district_data['is_running'] = is_running
            district_data['is_started'] = is_started
            for district in district_data['districts']:
                for candidate in district['candidates']:
                    candidate_name = candidate['name']['label']
                    for item in country_data['summary']['candidates']:
                        if item['name'] == candidate_name:
                            candidate['agreeTks'] = item['agreeTks']
                            candidate['disagreeTks'] = item['disagreeTks']
                            candidate['agreeRate'] = item['agreeRate']
                            candidate['disagreeRate'] = item['disagreeRate']
                            candidate['adptVictor'] = item['adptVictor']
                            candidate['ytpRate'] = item['ytpRate']
                            candidate['ntpRate'] = item['ntpRate']
                            break
            dump_2025_recall_data(bucket_name, filename.format(district_file), district_data)
        else:
            print(f"Failed to fetch data for {district_file}")

def get_202507_recall_data():
    running_data = request_cec('running.json')
    final_data = request_cec('final.json')
    is_started = True if final_data or running_data else False
    is_running = True if running_data and not final_data else False

    if not is_started and not is_running:
        return
    
    base_bucket_folder =  os.getenv('BASE_BUCKET_FOLDER_202507', 'elections-dev')
    base_url = f'https://whoareyou-gcs.readr.tw/{base_bucket_folder}' + '/2025/legislator/map/{}/recall-july/{}.json'
    recall_mapping = load_recall_mapping()
    constituencies, countries, counties = get_templates(base_url, recall_mapping)

    bucket_name = 'whoareyou-gcs.readr.tw'
    constituency_filename = base_bucket_folder + '/2025/legislator/map/constituency/recall-july/{}.json'
    country_filename = base_bucket_folder + '/2025/legislator/map/country/recall-july/country.json'
    county_filename = base_bucket_folder + '/2025/legislator/map/county/recall-july/{}.json'
    iframe_filename = base_bucket_folder + '/2025/legislator/iframe/recall-july/iframe.json'
    mobile_filename = base_bucket_folder + '/v2/2025/recall/district/{}.json'

    process_constituency_data(bucket_name, constituency_filename, constituencies, recall_mapping, is_started, is_running, final_data)

    country_data = process_country_data(bucket_name, country_filename, countries, recall_mapping, is_started, is_running, running_data, final_data)

    process_county_data(bucket_name, county_filename, counties, recall_mapping, is_started, is_running, running_data, final_data)
    
    process_iframe(base_bucket_folder, bucket_name, iframe_filename, countries, recall_mapping, is_started, is_running, running_data, final_data)
    
    process_mobile(base_bucket_folder, bucket_name, mobile_filename, is_started, is_running, country_data)

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

def dump_2025_recall_data(bucket_name, filename, data):
    data_upload_source = os.getenv('DATA_UPLOAD_SOURCE', 'gcs')
    if data_upload_source == 'gcs':
        upload_data(bucket_name, json.dumps(data, ensure_ascii=False).encode('utf8'), 'application/json', filename)
    elif data_upload_source == 'local':
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Dump {filename} successfully")
    else:
        print(f"Invalid data upload source: {data_upload_source}")

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
