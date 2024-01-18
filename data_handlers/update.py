'''
    Update the election result into WHORU GQL Server
'''
import os
import re
import data_handlers.gql.variable as variable
import data_handlers.gql.query as query
import data_handlers.helpers as hp
from data_handlers.gql.tool import gql_fetch, gql_update 
from tools.cec_data import request_url

gql_endpoint = os.environ['GQL_URL']
BUCKET = os.environ['BUCKET']          ### expected: whoareyou-gcs.readr.tw
ENV_FOLDER = os.environ['ENV_FOLDER']  ### expected: elections[-dev]

def update_person_election(year: str, election_type:str):
    '''
        Give the year of election, and update the person election result into WHORU database
    '''
    allowed_election_type = ['president', 'mountainIndigenous', 'plainIndigenous']
    if election_type not in allowed_election_type:
        print(f'election_type: {election_type} is not allowed')
        return False
    url_mapping = {
        'president': f'https://{BUCKET}/{ENV_FOLDER}/v2/{year}/president/all.json',
        'mountainIndigenous': f'https://{BUCKET}/{ENV_FOLDER}/v2/{year}/legislator/mountainIndigenous/all.json',
        'plainIndigenous': f'https://{BUCKET}/{ENV_FOLDER}/v2/{year}/legislator/plainIndigenous/all.json'
    }
    query_mapping = {
        'president': query.get_president_string(year),
        'mountainIndigenous': query.get_mountain_indigeous_string(year),
        'plainIndigenous': query.get_plain_indigeous_string(year)
    }

    ### Catch the v2 json, which records all the election result
    v2_url = url_mapping[election_type]
    raw_data = request_url(v2_url)
    if raw_data==None:
        print(f"Can't get v2 {election_type} json")
        return False
    v2_data = raw_data['candidates']

    ### Create the mapping table for id and candNo
    gql_presidents = gql_fetch(gql_endpoint, query_mapping[election_type])
    mapping = {} # {candNo: [id]}
    for data in gql_presidents['personElections']:
        id     = str(data['id'])
        candNo = str(data['number'])
        subId_list = mapping.setdefault(candNo, [])
        subId_list.append(id)
    
    ### Parse the data in v2
    for data in v2_data:
        candNo      = data['candNo']
        tks         = data['tks']
        tksRate     = data['tksRate']
        candVictor  = (data['candVictor']==True)
        ids = mapping.get(str(candNo), [])
        for id in ids:
            gql_variable = variable.PersonVariable(
                votes_obtained_number     = f'{tks}',
                votes_obtained_percentage = f'{tksRate}%',
                elected                   = candVictor,
                id                        = id
            ).to_json()
            result = gql_update(gql_endpoint, query.gql_update_person, gql_variable)
            show_update_person(result, election_type)
    return True

def update_party_election(year: str):
    '''
        Give the year of election, and update the party election result into WHORU database
    '''
    v2_url = f'https://{BUCKET}/{ENV_FOLDER}/v2/{year}/legislator/party/all.json'
    query_string = query.get_party_string(year)

    ### Catch the v2 json, which records all the election result
    raw_data = request_url(v2_url)
    if raw_data==None:
        print("Can't get v2 party json")
        return False
    v2_data = raw_data['parties']

    ### Create the mapping table for id and candNo
    gql_party = gql_fetch(gql_endpoint, query_string)
    mapping = {} # {candNo: [id]}
    for data in gql_party['organizationsElections']:
        id     = str(data['id'])
        candNo = str(data['number'])
        mapping[candNo] = id
    
    ### Parse the data in v2
    for data in v2_data:
        candNo       = data['candNo']
        tks          = data['tks']
        tksRate1     = data['tksRate1']
        tksRate2     = data['tksRate2']
        seats        = data['seats']
        id           = mapping.get(str(candNo), None)
        if id!=None:
            gql_variable = variable.PartyVariable(
                votes_obtained_number     = f'{tks}',
                first_obtained_number     = f'{tksRate1}%',
                second_obtained_number    = f'{tksRate2}%',
                seats                     = f'{seats}',
                id                        = id
            ).to_json()
            result = gql_update(gql_endpoint, query.gql_update_party, gql_variable)
            show_update_party(result)
    return True

def update_normal_election(year: str):
    '''
        Give the year of election, and update the normal election result into WHORU database
    '''
    v2_districts = hp.v2_electionDistricts
    gql_normal = gql_fetch(gql_endpoint, query.get_normal_string(year))
    mapping_normal_eid = create_normal_eid(gql_normal)

    for county_code, county_name in v2_districts.items():
        v2_url = f'https://{BUCKET}/{ENV_FOLDER}/v2/{year}/legislator/district/{county_name}.json'
        raw_data = request_url(v2_url)
        if raw_data==None:
            print(f"Can't get district v2 {county_name}.json")
            continue
        v2_districts = raw_data['districts']

        for district in v2_districts:
            area_code  = district['districtName']
            candidates = district['candidates']
            for candidate in candidates:
                candNo      = candidate['candNo']
                tks         = candidate['tks']
                tksRate     = candidate['tksRate']
                candVictor  = (candidate['candVictor']==True)
                eid = mapping_normal_eid.get(county_code, {}).get(area_code.zfill(2), {}).get(str(candNo), None)
                if eid != None:
                    gql_variable = variable.PersonVariable(
                        votes_obtained_number     = f'{tks}',
                        votes_obtained_percentage = f'{tksRate}%',
                        elected                   = candVictor,
                        id                        = eid
                    ).to_json()
                    result = gql_update(gql_endpoint, query.gql_update_person, gql_variable)
                    show_update_person(result, 'normal')
    return True

'''
    Some tool functions will help you organize or display the data
'''
def create_normal_eid(gql_constituency):
    '''
        Create mapping_normal_eid, which shows the hierarchy from city_code to candidates.
        eid means election_id.
        <Example>
            mapping_normal_eid = {
                '68000': {               => First level:  cityCode(countyCode) [string]
                    '01': {              => Second level: areaCode [string]
                        '1': election_id => Third level:  candNo [string]
                    }
                    ...
                }
                ...
            }
    '''
    mapping_normal_eid = {}
    person_data = gql_constituency['personElections']
    reverse_city_mapping = { value: key for key, value in hp.mapping_city.items() }
    pattern = r'\d+'  ###用來找選區編號
    for data in person_data:
        electionId = data['id']
        candNo     = data['number']
        city_code   = reverse_city_mapping[data['electoral_district']['city']]
        area_code   = re.findall(pattern, data['electoral_district']['name'])[0]

        subCity = mapping_normal_eid.setdefault(city_code, {})
        subArea = subCity.setdefault(area_code, {})
        subArea[candNo] = electionId
    return mapping_normal_eid

def show_update_person(result, election_type:str):
    if result:
        result  = result['item']
        id      = result['id']
        tks     = result['votes_obtained_number']
        tksRate = result['votes_obtained_percentage']
        elected = result['elected']
        print(f'Update {election_type} person id={id} to tks={tks}, tksRate={tksRate}, and elected={elected}')

def show_update_party(result):
    if result:
        result   = result['item']
        id       = result['id']
        tks      = result['votes_obtained_number']
        tksRate1 = result['first_obtained_number']
        tksRate2 = result['second_obtained_number']
        seats = result['seats']
        print(f'Update election party id={id} to tks={tks}, tksRate1={tksRate1}, tksRate2={tksRate2}, and seats={seats}')