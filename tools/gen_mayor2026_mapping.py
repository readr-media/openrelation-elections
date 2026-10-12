'''
工具:選前執行 2026-election-mapping(city / candidates 分頁)轉成 mayor2026 可直接讀的靜態 JSON
輸出到 mapping/2026/

用法:
    export GDRIVE_API_CREDENTIALS='{...service account json...}'
    python tools/gen_mayor2026_mapping.py

產出:
    mapping/2026/mayor_city.json       —— 22 縣市 mapping(照 SPEC_ORDER 排序)
    mapping/2026/mayor_candidate.json  —— { citycode: [{candNo,name,party}] } 候選人名冊
'''
import os
import json

import pygsheets

SHEET_ID = os.environ.get('MAYOR_SHEET_ID', '1Du6IegYW88a9aVeJgwLmwUXe5_tX4K5wh8WD28eOTOg')
CITY_TAB = os.environ.get('MAYOR_CITY_TAB', 'city')
CANDIDATE_TAB = os.environ.get('MAYOR_CANDIDATE_TAB', 'candidates')

# polling 順序(規格書指定)
SPEC_ORDER = [
    "63000", "65000", "68000", "66000", "67000", "64000",
    "10004", "10018", "10007", "10017", "10002", "10020",
    "10009", "10013", "10008", "10005", "10010", "10015",
    "10014", "10016", "09020", "09007",
]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(REPO_ROOT, 'mapping', '2026')
CITY_OUT = os.path.join(OUT_DIR, 'mayor_city.json')
CANDIDATE_OUT = os.path.join(OUT_DIR, 'mayor_candidate.json')


def open_sheet():
    '''授權並開啟 sheet (SA: gcs-account@mirrorlearning-161006)'''
    gc = pygsheets.authorize(service_account_env_var='GDRIVE_API_CREDENTIALS')
    return gc.open_by_key(SHEET_ID)


def read_sheet_records(sht, tab, header_key):
    '''讀指定分頁 → list of dict(值皆字串,保留前導零)
    自動找"含 header_key 的那列"當表頭,跳過上方任意說明列.'''
    wks = sht.worksheet_by_title(tab)
    rows = wks.get_all_values(include_tailing_empty=False,
                            include_tailing_empty_rows=False)
    hdr_idx = next(i for i, r in enumerate(rows) if header_key in [c.strip() for c in r])
    header = [h.strip() for h in rows[hdr_idx]]
    return [{header[i]: (r[i].strip() if i < len(r) else '') for i in range(len(header))}
            for r in rows[hdr_idx + 1:]]


def build_city(sht):
    '''city 分頁 → 22 縣市 mapping(照 SPEC_ORDER)'''
    by_code = {}
    for rec in read_sheet_records(sht, CITY_TAB, 'mnews-citycode'):
        cc = rec.get('mnews-citycode', '')
        if not cc:
            continue
        by_code[cc] = {
            'city': rec.get('city', ''),
            'prvCode': rec.get('cec-prvCode', '').zfill(2),
            'cityCode': rec.get('cec-cityCode', '').zfill(3),
        }
    mapping = []
    for i, cc in enumerate(SPEC_ORDER, 1):
        m = by_code.get(cc)
        if not m:
            raise ValueError(f"city tab missing citycode {cc}")
        mapping.append({'order': i, 'citycode': cc, **m})
    return mapping


def build_candidate(sht):
    '''candidates 分頁 → { citycode: [{candNo,name,party}] };跳過非 5 碼說明列'''
    roster = {}
    for rec in read_sheet_records(sht, CANDIDATE_TAB, 'candNo'):
        cc = rec.get('cityCode', '')
        if not (cc.isdigit() and len(cc) == 5):
            continue
        roster.setdefault(cc, []).append({
            'candNo': rec.get('candNo', '').zfill(2),   # 未抽籤前空值 → "00"(10/23抽籤,10/30提供後重跑)
            'name': rec.get('name', ''),
            'party': rec.get('party', ''),
        })
    return roster


def validate(city, candidate):
    '''確保 22 縣市都有候選人;缺漏或不足 2 位就擋(不產出殘缺名冊)>3 位僅警告'''
    problems = []
    for c in city:
        cc, name = c['citycode'], c['city']
        n = len(candidate.get(cc, []))
        if n == 0:
            problems.append(f"{name}({cc}) has no candidates")
        elif n < 2:
            problems.append(f"{name}({cc}) only {n} candidate(s) (mayor needs at least 2)")
        elif n > 3:
            print(f"[warn] {name}({cc}) has {n} candidates (spec expects 2-3, please check)")
    if problems:
        raise ValueError("roster validation failed, no files written:\n  " + "\n  ".join(problems))


def dump_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    sht = open_sheet()
    city = build_city(sht)
    candidate = build_candidate(sht)
    validate(city, candidate)
    os.makedirs(OUT_DIR, exist_ok=True)
    dump_json(CITY_OUT, city)
    dump_json(CANDIDATE_OUT, candidate)
    print(f"[gen] {CITY_OUT} ({len(city)} cities)")
    print(f"[gen] {CANDIDATE_OUT} ({sum(len(v) for v in candidate.values())} candidates / {len(candidate)} cities)")


if __name__ == '__main__':
    main()
