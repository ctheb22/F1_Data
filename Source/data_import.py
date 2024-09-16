import json
import requests
import os
import pandas as pd
from datetime import datetime, timedelta

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)
pd.set_option('display.width', 800)
pd.set_option('display.float_format', '{:,.2f}'.format)

class DataUtility:
    api_url_base = 'https://api.openf1.org/v1/'

    def generate_URL_and_file_path(self, api_call, params, format):
        url = api_call + '?' + '&'.join(['&%s=%s' % (key, params[key]) for key in sorted(params.keys())])

        file_path = 'Data/' + api_call
        if not os.path.exists(file_path):
            os.makedirs(file_path, exist_ok=True)
        file_path += '/' + '_'.join([key[0]+'-'+params[key] for key in sorted(params.keys())]) + '_' + api_call

        if format == 'json':
            file_path += '.json'
        else:
            file_path += '.csv'
            url += '&csv=true'
        return url, file_path

    def request(self, api_call, params, format, cache=True):
        #Get the url to be called and the file path to be written for this request.
        call_url, file_path = self.generate_URL_and_file_path(api_call, params, format=format)

        #json files are not automatically written to disk
        #caching will cause json files to be saved and/or referenced.
        if format == 'json':
            if not cache:
                #We're not caching, always request a new file.
                resp = self.request_json(self.api_url_base + call_url)
            elif not os.path.exists(file_path):
                #File doesn't exist yet, request and store it.
                resp = self.request_json(self.api_url_base + call_url)
                self.write_json_file(file_path, resp)
            else:
                #File exists, check if we need to refresh it
                if self.file_should_refresh(file_path):
                    resp = self.request_json(self.api_url_base + call_url)
                    self.write_json_file(file_path, resp)
                else:
                    resp = self.read_json_file(file_path)
            return resp
        #csv files are written to disk automatically as part of the request.
        #caching only changes whether we care about existing files.
        elif format == 'csv':
            if not cache:
                #We're not caching, ignore any local files
                self.request_csv(self.api_url_base + call_url, file_path)
            elif not os.path.exists(file_path):
                #File doesn't exist yet, request it.
                self.request_csv(self.api_url_base + call_url, file_path)
            else:
                #File exists, check if it needs a refresh.
                if self.file_should_refresh(file_path):
                    self.request_csv(self.api_url_base + call_url, file_path)
            return file_path
        else:
            #invalid format specified.
            raise ValueError(f'Invalid request format specified : {format}')

    def file_should_refresh(self, file_path):
        current_datetime = datetime.now()
        file_modified_datetime = datetime.fromtimestamp(os.path.getmtime(file_path))
        if current_datetime - timedelta(days=7) > file_modified_datetime:
            print("retrieving new file:\n\t" + file_path)
            return True
        else:
            print("Using existing file:\n\t" + file_path)
            return False

    def request_csv(self, call_url, file_path):
        with open(file_path, 'wb') as f, \
                requests.get(call_url, stream=True) as r:
            for line in r.iter_lines():
                f.write(line + '\n'.encode())

    def request_json(self, call_url):
        with requests.get(call_url) as r:
            request_json = r.json()
        return request_json

    def write_json_file(self, file_path, python_object):
        with open(file_path, 'w') as f:
            json.dump(python_object, f)

    def read_json_file(self, file_path):
        with open(file_path, 'r') as openfile:
            json_object = json.load(openfile)
        return json_object

    def request_sessions(self, params, format='json'):
        return self.request('sessions', params, format=format)

    def request_drivers(self, params, format='json'):
        return self.request('drivers', params, format=format, cache=True)

    def request_laps(self, params, format='json'):
        return self.request('laps', params, format=format, cache=True)

    def request_stints(self, params, format='json'):
        return self.request('stints', params, format=format, cache=True)

    def get_driver_params(self, name_acronym='', driver_number=-1, year=0, session_name='', circuit=''):
        params = {}
        if not name_acronym and driver_number < 0:
            raise ValueError('No driver specified.')
        elif not name_acronym:
            params['driver_number'] = str(driver_number)
        else:
            params['name_acronym'] = name_acronym

        if year != 0:
            params['year'] = str(year)

        if session_name:
            params['session_name'] = session_name

        if circuit:
            params['circuit_short_name'] = circuit

        return params

    def clean_df(self, df):
        # remove stints/laps where the tire compound is marked as "unknown"
        df = df.loc[df['compound'].isin(['SOFT', 'HARD', 'MEDIUM', 'INTERMEDIATE', 'WET'])]
        df = df.loc[df['session_name'] == 'Race']
        return df

    def combine_laps_and_session(self, lapdf, sessiondf):
        def generate_laps_list(start, end):
            if start == end:
                return [start]
            return [i for i in range(start, end+1)]
        sessiondf['lap_number'] = sessiondf.apply(lambda x: generate_laps_list(x.lap_start, x.lap_end), axis=1)
        sessiondf = sessiondf.explode('lap_number', ignore_index=True)
        sessiondf['lap_in_stint'] = sessiondf['lap_number'] - sessiondf['lap_start'] + 1

        fulldf = lapdf.merge(sessiondf, on=['session_key', 'driver_number', 'lap_number'])
        return self.clean_df(fulldf)

    def get_all_laps_and_sessions_per_year_df(self, year):
        '''
        :param year: the year we're interested in.
        :return: lapdf of all laps for races and sprints for the given year, sessiondf containing all metadata for a all sessions (race/sprints)
        '''

        cached_laps_path = f'Data/' + str(year) + '_laps_master.csv'
        cached_session_path = f'Data/' + str(year) + '_session_master.csv'
        if os.path.exists(cached_laps_path) and os.path.exists(cached_session_path):
            return self.combine_laps_and_session(pd.read_csv(cached_laps_path), pd.read_csv(cached_session_path))

        #This is a sort of odd request (no params); manually constructing it rather than going through existing methods
        print('Getting stints')
        stint_url = 'stints?&csv=true'
        file_path = 'Data/stints'
        if not os.path.exists(file_path):
            os.makedirs(file_path, exist_ok=True)
        file_path += f'/{year}_stints.csv'
        # File exists, check if it needs a refresh.
        if not os.path.exists(file_path):
            self.request_csv(self.api_url_base + stint_url, file_path)
        stintdf = pd.read_csv(file_path)
        print(f'{len(stintdf)} stints retrieved.')
        print('...\nGetting sessions')
        #Get all sessions for a given year.
        sessiondf = pd.read_csv(self.request_sessions({'year':str(year)}, format='csv'))
        print(f'{len(sessiondf)} sessions retrieved.')
        #filter by "Race" events (includes Sprints)
        sessiondf = sessiondf[sessiondf['session_type'] == 'Race']
        print(f'Filtered down to {len(sessiondf)} race and sprint sessions')
        print(sessiondf)


        lap_list = []
        driver_list = []
        print('Building driver and lap lists:')
        i = 1
        for sesh in sessiondf['session_key']:
            print(f'{i}/{len(sessiondf)} session ({sesh}):')
            i+=1
            key_params = {'session_key': str(sesh)}
            t_l_df = pd.read_csv(self.request_laps(key_params, format='csv'))
            t_d_df = pd.read_csv(self.request_drivers(key_params, format='csv'))
            print(f'\t{str(sesh)} laps & drivers retrieved:')
            print(f'\t\t{len(t_l_df)} laps retrieved.')
            print(f'\t\t{len(t_d_df)} drivers retrieved.')
            lap_list.append(t_l_df)
            driver_list.append(t_d_df)
        lapdf = pd.concat(lap_list, ignore_index=True)
        driverdf = pd.concat(driver_list, ignore_index=True)
        print(f'{len(lapdf)} total laps retrieved')
        print(f'{len(driverdf)} total driver records retrieved')

        #build the final sessiondf:
        sessiondf = pd.merge(sessiondf, driverdf, on=['session_key'])
        sessiondf = pd.merge(sessiondf, stintdf, on=['session_key', 'driver_number'])
        print(f'{len(sessiondf)} total session records (should be 1 for every driver, stint, session combo)')

        print('caching built dfs.')

        sessiondf['stint_length'] = sessiondf['lap_end'] - sessiondf['lap_start'] + 1
        sessiondf = sessiondf[['session_key','circuit_short_name','session_name','driver_number','stint_number',
                               'country_name','date_start','year','full_name','name_acronym','team_colour',
                               'team_name','compound','lap_end','lap_start','stint_length','tyre_age_at_start']]
        sessiondf.rename(columns={'country_name': 'session_country', 'full_name':'driver_name', 'name_acronym':'driver_short',
                          'tyre_age_at_start':'initial_tire_age', 'circuit_short_name':'track_name', 'date_start':'date'}, inplace=True)

        lapdf.rename(columns={'date_start': 'date','duration_sector_1':'sector_1','duration_sector_2':'sector_2',
                      'duration_sector_3':'sector_3','lap_duration':'lap_seconds','segments_sector_1':'s1_segs',
                      'segments_sector_2':'s2_segs','segments_sector_3':'s3_segs'}, inplace=True)


        sessiondf.to_csv(cached_session_path, index=False)
        lapdf.to_csv(cached_laps_path, index=False)

        return self.combine_laps_and_session(lapdf, sessiondf)



