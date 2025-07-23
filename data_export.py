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
    #voting_data['title'] = meta_sheet.get_value("B2")       
    get_cec_data = meta_sheet.get_value("B2")
    display_iframe = meta_sheet.get_value("B3")  # 讀取 display_iframe
    if get_cec_data == 'T':
        cec_json = requests.get('https://whoareyou-gcs.readr.tw/elections-dev/2025/legislator/iframe/recall-july/iframe.json')
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
        votePop_local = 'votePop.json'
        votePop_map = {}
        # 只有本地沒有 votePop.json 時才去下載 iframe_data.json 來補
        if not os.path.exists(votePop_local):
            iframe_url = 'https://whoareyou-gcs.readr.tw/elections-dev/2025/legislator/iframe/recall-july/iframe.json'
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
    recallno_mapping_json = requests.get('https://whoareyou-gcs.readr.tw/elections-dev/candNo-mapping/202507_recallno_mapping.json')
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
        tboxNo = district['vill']
        tboxNo_int = int(tboxNo) if tboxNo.isdigit() else tboxNo
        data = None if cec_data is None or deptCode not in cec_data or tboxNo_int not in cec_data[deptCode] else cec_data[deptCode][tboxNo_int]
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

def transform_cec_data_with_tbox_no(cec_data, candidate):
    if cec_data is None:
        return None
    
    data = {}
    for vill_status in cec_data[candidate]:
        dept_code = vill_status['deptCode']
        tbox_no = vill_status['tboxNo']
        
        if dept_code not in data:
            data[dept_code] = {}
        
        data[dept_code][tbox_no] = vill_status
    
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

def get_updated_at(country_data, cec_data):
    if cec_data is None:
        return country_data['updatedAt']
    else:
        return format_202507_timestamp(cec_data['ST'])

def process_constituency_data(constituencies, recall_mapping, is_started, is_running, final_data):
    for constituency in constituencies:
        cec_data = final_data if is_started & (not is_running) else None
        updatedAt = constituency[2]['updatedAt'] if cec_data is None else format_202507_timestamp(cec_data['ST'])
        # TODO: have bug...
        cec_data = transform_cec_data_with_tbox_no(cec_data, find_candidate_no(recall_mapping, constituency[0], constituency[1]))
        districts = parse_202507_constituency_data(constituency[2], cec_data)
        data = {
            'updatedAt': updatedAt,
            'is_running': is_running,
            'is_started': is_started,
            'districts': districts
        }
        upload_data(
            'whoareyou-gcs.readr.tw',
            json.dumps(data, ensure_ascii=False).encode('utf8'),
            'application/json',
            f'elections-dev/2025/legislator/map/constituency/recall-july/{constituency[0]}{constituency[1]}.json'
        )

def process_country_data(countries, recall_mapping, is_started, is_running, running_data, final_data):
    country_data = countries[1]
    country_data_summary = country_data['summary']
    country_data_districts = country_data['districts']
    
    cec_data = None if not is_started else running_data if is_running else final_data
    
    gmeb_data, prof_count_data, candidate_data = calculate_statistics_by_country(cec_data, recall_mapping)
    
    update_summary_data(country_data_summary, candidate_data, cec_data, prof_count_data, gmeb_data)
    
    update_districts_data(country_data_districts, candidate_data, cec_data, prof_count_data, gmeb_data)
    
    data = {
        'updatedAt': get_updated_at(country_data, cec_data),
        'is_running': is_running,
        'is_started': is_started,
        'summary': country_data_summary,
        'districts': country_data_districts
    }
    
    upload_data(
        'whoareyou-gcs.readr.tw',
        json.dumps(data, ensure_ascii=False).encode('utf8'),
        'application/json',
        'elections-dev/2025/legislator/map/country/recall-july/country.json'
    )

def process_county_data(counties, recall_mapping, is_started, is_running, running_data, final_data):
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

        upload_data(
            'whoareyou-gcs.readr.tw',
            json.dumps(data, ensure_ascii=False).encode('utf8'),
            'application/json',
            f'elections-dev/2025/legislator/map/county/recall-july/{county}.json'
        )

def process_iframe(countries, recall_mapping, is_started, is_running, running_data, final_data):
    cec_data = None if not is_started else running_data if is_running else final_data
    country_data = countries[1]
    if cec_data:
        gmeb_data, prof_count_data, candidate_data = calculate_statistics_by_country(cec_data, recall_mapping)
        update_summary_data(country_data['summary'], candidate_data, cec_data, prof_count_data, gmeb_data)
    
    candidates_template = country_data['summary']['candidates']
    
    candidate_names = {}
    
    all_candidate_numbers = set()
    for areas in recall_mapping.values():
        for item in areas:
            candidate_no = item.get('no')
            if candidate_no:
                all_candidate_numbers.add(candidate_no)
    
    sorted_candidates = sorted(all_candidate_numbers)
    
    for i, candidate_no in enumerate(sorted_candidates):
        if i < len(candidates_template):
            candidate_names[candidate_no] = candidates_template[i]['name']
    
    if cec_data and 'A25' in cec_data:
        candidate_names['A25'] = '高虹安'
    
    all_candidates = set()
    for areas in recall_mapping.values():
        for item in areas:
            candidate_no = item.get('no')
            if candidate_no:
                all_candidates.add(candidate_no)
    
    if cec_data:
        for candidate_no in cec_data.keys():
            if candidate_no.startswith('A'):
                all_candidates.add(candidate_no)
    
    result = []
    
    for candidate_no in sorted(all_candidates):
        candidate_name = candidate_names.get(candidate_no, f'候選人{candidate_no}')
        
        candidate_vote = None
        if cec_data and candidate_no in cec_data:
            candidate_vote = find_candidate_vote_data(cec_data[candidate_no])
        
        template_candidate = None
        if candidate_vote:
            for cand in candidates_template:
                if (cand['agreeTks'] == candidate_vote['agreeTks'] and 
                    cand['disagreeTks'] == candidate_vote['disagreeTks']):
                    template_candidate = cand
                    break
        
        if template_candidate:
            result.append({
                'name': candidate_name,
                'votePop': candidate_vote.get('gmeb', 0) if candidate_vote else 0,
                'agreeTks': template_candidate['agreeTks'],
                'disagreeTks': template_candidate['disagreeTks'],
                'ytpRate': template_candidate['ytpRate'],
                'ntpRate': template_candidate['ntpRate'],
                'adptVictor': template_candidate['adptVictor']
            })
        elif candidate_vote:
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
    
    upload_data(
        'whoareyou-gcs.readr.tw',
        json.dumps(data, ensure_ascii=False).encode('utf8'),
        'application/json',
        'elections-dev/2025/legislator/iframe/recall-july/iframe.json'
    )

def get_202507_recall_data():
    final_data = request_cec('final.json')
    running_data = request_cec('running.json')
    is_started = True if final_data or running_data else False
    is_running = True if running_data and not final_data else False

    if not is_started and not is_running:
        return
    
    base_url = 'https://whoareyou-gcs.readr.tw/elections-dev/2025/legislator/map/{}/recall-july/{}.json'
    recall_mapping = load_recall_mapping()
    constituencies, countries, counties = get_templates(base_url, recall_mapping)

    process_constituency_data(constituencies, recall_mapping, is_started, is_running, final_data)

    process_country_data(countries, recall_mapping, is_started, is_running, running_data, final_data)

    process_county_data(counties, recall_mapping, is_started, is_running, running_data, final_data)
    
    process_iframe(countries, recall_mapping, is_started, is_running, running_data, final_data)


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
