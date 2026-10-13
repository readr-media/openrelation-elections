'''
2026 縣市長開票即時轉檔:讀電視 SQLite + 中選會 → 逐縣市揉合 → iframe.json → GCS.
輸入:電視 .db(P1/P1_V),中選會 running/final,mapping/2026 靜態 JSON,上一輪 iframe.json(latch).
輸出:{ENV_FOLDER}/2026/mayor/iframe.json(UTF-8 無 BOM).
名冊 JSON 由 tools/gen_mayor2026_mapping.py 選前離線產生.
'''
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta

from google.cloud import storage
from data_export import download_sqlite_from_gcs, upload_data
from tools.cec_data import request_cec

# ── 環境變數 ──
BUCKET = os.environ['BUCKET']                  # 輸出 bucket
ENV_FOLDER = os.environ['ENV_FOLDER']          # elections-dev / elections

# 電視 .db:gs://statics-editools-prod/2026/{MMDD}.db(來源公開唯讀)
TV_DB_BUCKET = 'statics-editools-prod'
TV_DB_NAME = os.environ.get('TV_DB_NAME', '2026/1128.db')

YEAR = 2026
TZ = timezone(timedelta(hours=8))

OUTPUT_PATH = f'{ENV_FOLDER}/{YEAR}/mayor/iframe.json'

# 靜態名冊(由 tools/gen_mayor2026_mapping.py 產生;已含 SPEC_ORDER 排序)
MAPPING_DIR = os.path.join(os.path.dirname(__file__), 'mapping', str(YEAR))
CITY_JSON = os.path.join(MAPPING_DIR, 'mayor_city.json')
CANDIDATE_JSON = os.path.join(MAPPING_DIR, 'mayor_candidate.json')

SOURCE_MNEWS = '鏡新聞自行計票'
SOURCE_CEC = '中央選舉委員會'

# isStarted:達此時間視為開始開票(TODO:確認開票時間)
ELECTION_START = os.environ.get('MAYOR_START_TS', '2026-11-28 16:00:00')

_storage_client = None


def gcs_client():
    '''共用 storage client'''
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


### ---------- util ----------
def to_int(v):
    '''字串轉 int; 空 / 找不到為 None.'''
    if v is None or v == '':
        return None
    try:
        return int(str(v).replace(',', ''))
    except ValueError:
        return None


def to_float(v):
    '''字串轉 float; 空 / 找不到為 None.'''
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace(',', '').replace('%', ''))
    except ValueError:
        return None


def format_st(st):
    '''中選會 ST(MMDDHHMMSS) → "2026-MM-DD HH:MM:SS";格式錯誤回 None.'''
    try:
        dt = datetime.strptime(str(st), '%m%d%H%M%S')
    except (ValueError, TypeError):
        return None
    return f"{YEAR}-{dt.strftime('%m-%d %H:%M:%S')}"


def parse_cec_mayor(tc):
    '''中選會 TC → { region: {candNo(int): candTksInfo, 'profRate': x} }(取縣市總計層,deptCode 空→'000').
    candNo 轉為 int 當 key,避免 CEC 回字串/整數不一致造成查不到.'''
    organized = {}
    for d in tc:
        dept = d['deptCode'] if d.get('deptCode') else '000'
        region = f"{d['prvCode']}_{d['cityCode']}_{dept}"
        node = organized.setdefault(region, {'profRate': d.get('profRate')})
        for c in d.get('candTksInfo', []):
            no = to_int(c.get('candNo'))
            if no is not None:
                node[no] = c
    return organized


def _read_mapping_json(path, name):
    '''讀靜態名冊;缺檔給明確訊息(提示先跑 gen tool).'''
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{name} not found: {path}; run tools/gen_mayor2026_mapping.py first to generate and deploy the mapping")
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_mapping():
    '''讀 mapping/2026/mayor_city.json → 22 縣市 mapping(已含 SPEC_ORDER 排序).'''
    return _read_mapping_json(CITY_JSON, 'city mapping')


def load_roster():
    '''讀 mapping/2026/mayor_candidate.json → { citycode: [{candNo,name,party}] }.'''
    return _read_mapping_json(CANDIDATE_JSON, 'candidate roster')


def read_prev():
    '''讀上一輪輸出當 latch.blob 不存在回 {}(第一輪);讀取/解析失敗回 None(呼叫端跳過本輪,避免 latch 被歸零).'''
    try:
        blob = gcs_client().bucket(BUCKET).get_blob(OUTPUT_PATH)
    except Exception as e:
        print(f"[read_prev] failed to read previous output: {type(e).__name__}: {e}")
        return None
    if blob is None:
        return {}
    try:
        return json.loads(blob.download_as_bytes())
    except Exception as e:
        print(f"[read_prev] failed to parse previous output: {type(e).__name__}: {e}")
        return None


### ---------- 電視 SQLite ----------
def read_tv_db():
    '''下載讀電視 .db → (p1={citycode:{candNo:tks}}, p1v={citycode:{ems,candvictor}}, db_time);
    db_time=.db 上傳 GCS 的時間(電視來源 updatedAt 用);失敗回 (None, None, None).'''
    try:
        db_path = 'mayor.db'
        download_sqlite_from_gcs(TV_DB_BUCKET, TV_DB_NAME, db_path)
        try:                                   # 取上傳時間失敗不丟整輪,改用當下時間
            blob = gcs_client().bucket(TV_DB_BUCKET).blob(TV_DB_NAME)
            blob.reload()                      # 只抓 metadata
            db_time = blob.updated.astimezone(TZ)
        except Exception as e:
            print(f"[read_tv_db] failed to get .db upload time, using current time: {type(e).__name__}: {e}")
            db_time = datetime.now(TZ)
        snapshot_tv_db(db_path)                # 固定備份
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        p1 = {}
        for citycode, candno, tks in cur.execute("SELECT citycode, candno, tks FROM P1"):
            p1.setdefault(citycode, {})[int(candno)] = tks
        p1v = {}
        for citycode, ems, candvictor in cur.execute("SELECT citycode, ems, candvictor FROM P1_V"):
            p1v[citycode] = {'ems': ems, 'candvictor': candvictor}
        conn.close()
        return p1, p1v, db_time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"[read_tv_db] failed to read TV DB: {type(e).__name__}: {e}")
        return None, None, None


### ---------- 備份(固定開啟上傳 GCS)----------
def snapshot_cec(data, filename):
    '''中選會原始檔備份 → cec-data/2026/{原檔名}-{YYYYMMDD_HHMMSS}.json.'''
    if not data:
        return
    try:
        ts = datetime.now(TZ).strftime('%Y%m%d_%H%M%S')
        stem = os.path.splitext(filename)[0]           # running.json → running
        dest = f'{ENV_FOLDER}/cec-data/{YEAR}/{stem}-{ts}.json'
        upload_data(BUCKET, json.dumps(data, ensure_ascii=False).encode('utf8'),
                    'application/json', dest)
    except Exception as e:
        print(f"[snapshot cec] failed: {type(e).__name__}: {e}")


def snapshot_tv_db(local_path):
    '''電視 .db 備份 → statics-editools-prod/2026/backup/{原檔名}-{YYYYMMDD_HHMMSS}.db'''
    try:
        ts = datetime.now(TZ).strftime('%Y%m%d_%H%M%S')
        stem = os.path.splitext(os.path.basename(TV_DB_NAME))[0]   # 2026/1128.db → 1128
        dest = f'{YEAR}/backup/{stem}-{ts}.db'
        gcs_client().bucket(TV_DB_BUCKET).blob(dest).upload_from_filename(local_path)
    except Exception as e:
        print(f"[snapshot db] failed: {type(e).__name__}: {e}")


### ---------- candVictor ----------
def highest_tks_candno(candidates):
    valid = [c for c in candidates if c['tks'] is not None]
    return max(valid, key=lambda c: c['tks'])['candNo'] if valid else None


def set_victor(candidates, candno):
    for c in candidates:
        c['candVictor'] = (c['candNo'] == candno)


def mark_victor(candidates, city, citycode, p1v, cec, region, isRunning, prev_victor):
    '''
    每縣市至多一位:
      開票中:電視 candvictor=1 → 取最高票,先標先鎖.
      結束:以中選會 '*' 為準(覆蓋電視);CEC 未給則留上一輪.
    '''
    if not isRunning:                       # 結束:中選會 '*' 為準
        for no, info in (cec.get(region) or {}).items():
            if isinstance(info, dict) and str(info.get('candVictor', '')).strip() == '*':
                set_victor(candidates, str(no).zfill(2))
                return
        if prev_victor.get(city):          # CEC 未給 → 留上一輪
            set_victor(candidates, prev_victor[city])
        return

    locked = prev_victor.get(city)         # 開票中:先標先鎖
    if locked:
        set_victor(candidates, locked)
        return
    if str((p1v.get(citycode) or {}).get('candvictor', 0)) == '1':
        winner = highest_tks_candno(candidates)
        if winner:
            set_victor(candidates, winner)


### ---------- 主流程 ----------
def mayor2026_realtime():
    now = datetime.now(TZ)

    # 上一輪 JSON(latch:isRunning / source / candVictor) — 先讀,才能決定要不要抓 final
    prev = read_prev()
    if prev is None:        # 讀取失敗(非不存在) → 跳過本輪,不寫出,避免把 latch 歸零成第一輪
        print('[mayor2026] cannot read previous output, skip this round')
        return {}
    prev_isRunning = prev.get('isRunning', True)
    prev_source, prev_victor = {}, {}
    for p in prev.get('polling', []):
        prev_source[p['city']] = p.get('source')
        for c in p.get('candidates', []):
            if c.get('candVictor'):
                prev_victor[p['city']] = c['candNo']

    # 抓中選會 + 備份:running/final 只在尚未結束時抓(結束後已 latch,不再請求,避免每輪下載)
    if prev_isRunning is not False:
        running = request_cec('running.json')
        final = request_cec('final.json')
    else:
        running = final = None
    snapshot_cec(running, 'running.json')
    snapshot_cec(final, 'final.json')
    cec_new = bool(running or final)

    # isStarted(時間)/ isRunning(final 出現或上輪已結束 → 永久 false)
    try:
        start_dt = datetime.strptime(ELECTION_START, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
    except ValueError:
        start_dt = datetime(YEAR, 11, 28, 16, 0, 0, tzinfo=TZ)
        print(f"[mayor2026] invalid MAYOR_START_TS ({ELECTION_START!r}), falling back to default {YEAR}-11-28 16:00:00")
    isStarted = (now >= start_dt) or prev.get('isStarted', False)
    isRunning = not (prev_isRunning is False or bool(final))

    # 讀mapping json 和電視 DB, DB 取不到則跳過(保留上一輪,不寫殘缺)
    mapping = load_mapping()
    roster = load_roster()
    p1, p1v, tv_time = read_tv_db()
    cec_src = final or running
    if not p1 or not p1v:
        # 結束後全縣市走中選會、用不到 TV 資料 → 有 CEC 就用空 p1/p1v 往下產出,
        # 避免 final 首現那輪 TV DB 剛好掛時,final 票數與 '*' 當選一直寫不進去.
        if not isRunning and cec_src and 'TC' in cec_src:
            p1, p1v, tv_time = {}, {}, now.strftime('%Y-%m-%d %H:%M:%S')
        else:
            print('[mayor2026] TV DB empty/unreadable, skip this round')
            return prev

    # 中選會票數(縣市總計層)
    cec = parse_cec_mayor(cec_src['TC']) if (cec_src and 'TC' in cec_src) else {}

    # 逐縣市 source(ems latch;開票前鏡新聞,結束中選會)
    sources = {}
    for county in mapping:
        city = county['city']
        ems = (p1v.get(county['citycode']) or {}).get('ems', 0)
        src = SOURCE_CEC if (prev_source.get(city) == SOURCE_CEC or str(ems) == '1') else SOURCE_MNEWS
        if not isStarted:
            src = SOURCE_MNEWS
        elif not isRunning:
            src = SOURCE_CEC
        sources[city] = src

    # 無新 CEC 且全部都是中選會縣市 → 沒東西可更新,整輪凍住(不覆寫)
    if not cec_new and all(s == SOURCE_CEC for s in sources.values()):
        print('[mayor2026] no new CEC and all cities on CEC, freeze this round')
        return prev

    # 逐縣市產出(照 SPEC_ORDER);updatedAt 逐縣市:中選會使用ST,電視使用.db 上傳時間
    cec_time = (format_st(cec_src['ST']) if (cec_src and cec_src.get('ST')) else None) or tv_time
    prev_polling = {p['city']: p for p in prev.get('polling', [])}
    polling = []
    for county in mapping:
        citycode, city = county['citycode'], county['city']
        region = f"{county['prvCode']}_{county['cityCode']}_000"
        source = sources[city]
        use_cec = (source == SOURCE_CEC)

        # 中選會縣市但本輪無新 CEC → 沿用上一輪該縣市(凍住不覆寫),TV 縣市照算
        if use_cec and not cec_new and city in prev_polling:
            polling.append(prev_polling[city])
            continue

        candidates = []
        for cand in sorted(roster.get(citycode, []), key=lambda x: int(x['candNo'])):
            no_int = int(cand['candNo'])
            if not isStarted:
                # 開票前:tks/tksRate 皆 null,absTksRate 補 0.0
                tks, tksRate, absTksRate = None, None, 0.0
            elif use_cec:
                info = (cec.get(region) or {}).get(no_int, {})
                # 中選會:tks 取 TC.tks(找不到為 null);tksRate/absTksRate 皆取中選會得票率(2位;absTksRate 缺值補0.0)
                tks = to_int(info.get('tks'))
                rate = to_float(info.get('tksRate'))
                tksRate = round(rate, 2) if rate is not None else None
                absTksRate = round(rate, 2) if rate is not None else 0.0
            else:
                # 鏡新聞(電視):tks 取 P1.tks(找不到為 null);tksRate 一律 null;absTksRate 一律 0.0
                tks = to_int((p1.get(citycode) or {}).get(no_int))
                tksRate = None
                absTksRate = 0.0
            candidates.append({
                'candNo': str(no_int).zfill(2), 'name': cand['name'], 'party': cand['party'],
                'tks': tks, 'absTksRate': absTksRate, 'tksRate': tksRate, 'candVictor': False,
            })

        mark_victor(candidates, city, citycode, p1v, cec, region, isRunning, prev_victor)
        updatedAt = cec_time if use_cec else tv_time
        polling.append({'city': city, 'candidates': candidates, 'updatedAt': updatedAt, 'source': source})

    # 上傳(UTF-8 無 BOM);updatedAt 已移入各縣市與 source 同層
    out = {'isStarted': isStarted, 'isRunning': isRunning, 'polling': polling}
    upload_data(BUCKET, json.dumps(out, ensure_ascii=False).encode('utf8'),
                'application/json', OUTPUT_PATH)
    return out


if __name__ == '__main__':
    print(json.dumps(mayor2026_realtime(), ensure_ascii=False, indent=2))
