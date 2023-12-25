import os
import data_handlers.parser    as parser
import data_handlers.president.generator as pd_generator
import data_handlers.legislator.generator as lg_generator
import data_handlers.helpers as hp

from tools.uploadGCS import upload_blob, save_file, upload_multiple_test
from datetime import datetime

def pipeline_2024(raw_data, is_started: bool=True, is_running: bool=False):
    result = True
    ### Generate data for president
    result = pipeline_president_2024(
        raw_data, 
        is_started = is_started,
        is_running = is_running
    )
    ### Generate data for legislator
    result = pipeline_legislator_constituency_2024(
        raw_data,
        is_started = is_started,
        is_running = is_running
    )
    result = pipeline_legislator_special_2024(
        raw_data,
        is_started = is_started,
        is_running = is_running
    )
    result = pipeline_legislator_party_2024(
        raw_data,
        None,      ### We just pass it when we have final_A.json
        is_started=is_started,
        is_running=is_running
    )
    return result

def pipeline_president_2024(raw_data, is_started: bool=True, is_running: bool=False):
    year = datetime.now().year
    root_path = os.path.join(os.environ['ENV_FOLDER'], '2024', 'president', 'map')
    parsed_county = parser.parse_county(raw_data)
    
    ### Parse and store country
    country_json  = pd_generator.generate_country_json(
        preprocessing_data = parsed_county, 
        is_running = is_running,
        is_started = is_started    
    )
    filename = os.path.join(root_path, 'country', 'country.json')
    save_file(filename, country_json)
    upload_blob(filename, year)

    ### Parse and store county
    generated_county_json = pd_generator.generate_county_json(
        preprocessing_data = parsed_county,
        is_running = is_running,
        is_started = is_started
    )
    for county_code, county_json in generated_county_json.items():
        filename = os.path.join(root_path, 'county', county_code)
        save_file(filename, county_json)
        upload_blob(filename, year)

    ### Parse town
    if is_running == False:
        county_codes = list(parsed_county['districts'].keys())
        county_codes.remove(hp.COUNTRY_CODE)        ### 移除全國代碼
        county_codes.remove(hp.FUJIAN_PRV_CODE)     ### 移除福建省碼
        
        result = []
        updateAt = parsed_county.get('updateAt', None)
        for county_code in county_codes:
            county_data         = parsed_county['districts'].get(county_code, None)
            town_data           = parser.parse_town(county_code, county_data)
            vill_data, errors   = pd_generator.generate_town_json(town_data, updateAt, is_running, is_started)
            result.append(vill_data)
            # You can use errors to track the problematic tboxNo
        for vill_data in result:
            for key, value in vill_data.items():
                filename = os.path.join(root_path, 'town', key)
                save_file(filename, value)
                upload_blob(filename, year)
    # TODO: Upload multiple data
    upload_multiple_test(year)
    return True

def pipeline_legislator_constituency_2024(raw_data, is_started: bool=True, is_running: bool=False):
    year = datetime.now().year
    root_path = os.path.join(os.environ['ENV_FOLDER'], '2024', 'legislator', 'map', 'constituency', 'normal')
    parsed_area = parser.parse_constituency_area(raw_data)
    constituency_result = lg_generator.generate_constituency_json(parsed_area, False, True)
    for filename, data in constituency_result.items():
        save_file(os.path.join(root_path, filename), data)
        upload_blob(filename, year)
    return True

def pipeline_legislator_special_2024(raw_data, is_started: bool=True, is_running: bool=False):
    '''
        In this pipeline, we generate mountain and plain indigenous in one pipeline
    '''
    year = datetime.now().year
    root_path = os.path.join(os.environ['ENV_FOLDER'], '2024', 'legislator', 'map')
    
    ### Generate country.json
    for election_type in ['mountainIndigenous', 'plainIndigenous']:
        parsed_county = parser.parse_county(raw_data, election_type)
        country_json  = lg_generator.generate_country_json(parsed_county, is_running, is_started, election_type)
        
        filename = os.path.join(root_path, 'country', election_type)
        save_file(filename, country_json)
        upload_blob(filename, year)
    return True

def pipeline_legislator_party_2024(raw_data, final_A, is_started: bool=True, is_running: bool=False):
    year = datetime.now().year
    root_path = os.path.join(os.environ['ENV_FOLDER'], '2024', 'legislator', 'map')
    election_type = 'party'
    
    if final_A!=None:
        parser.parse_seat(final_A, hp.mapping_party_seat) ### 將席次統計結果寫入對照表
    
    parsed_county = parser.parse_county(raw_data, election_type)
    country_json  = lg_generator.generate_country_json(parsed_county, is_running, is_started, election_type)

    filename = os.path.join(root_path, 'country', election_type)
    save_file(filename, country_json)
    upload_blob(filename, year)
    return True