import pandas as pd


class DataFormatter:
    def remove_invalid_lap_times(self, df):
        """
        Function to remove invalid, excessively high lap times, as well as pit out laps and laps
        where we infer that a field slowing even occurred (yellow flag, etc...).

        :param df: full dataframe of lap times.
        :return: new dataframe with invalid lap times removed.

        THIS CAN SKEW PER STINT ANALYSIS.
        This has the potential (and is likely to) cut out whole stints, particularly at the
        beginning of the race, where a driver may pit on the first lap.
        """
        #

        # We're doing an arbitrary time calculation to find the limit for outlier laps
        sddf = (df.groupby(['session_key', 'driver_name'])
                .agg({'lap_seconds': 'median',
                      'lap_number': 'count'}))
        sddf = sddf.rename(columns={'lap_number': 'session_laps'})
        sddf['valid_lap_threshold'] = sddf['lap_seconds']*1.25
        sddf = sddf[['session_laps', 'valid_lap_threshold']]
        dfr = df.merge(sddf, on=['driver_name', 'session_key'])

        #Set the total race laps per session. We have to assume this based on lap_number data, since this is not retrievable from the endpoint.
        # We find the maximum number of laps completed, which in almost all cases should be the total laps. Exceptions would be races that got rained out
        # or hit the maximum race time midway through. In these cases, we still need to assume a reasonable total lap count, because we use it later on for
        # calculating normalized lap times taking fuel weight into account.
        # If less than 44 laps were completed (the shortest lap count) we assume the lap count is the average (and most common lap count), 57.
        # There is certainly still the possibility of a race being rained out after 44 laps, and not getting the correct total laps, but this is a rare edge case that we ignore.
        dfs = dfr.groupby('session_key').agg({'session_laps': 'max'})
        dfs['total_session_laps'] = dfs['session_laps'].apply(lambda x: x if x > 44 else 57)
        dfr = dfr.merge(dfs, on=['session_key'])

        # Here we used the calculated outlier lap limit to mark a lap valid or not.
        # We then use the collected lap validity column to find common invalid laps, which might indicates an event (yellow flag, etc..)
        # that caused these specific laps to be slow for multiple drivers. We use the 'field_valid_lap' column to mark these laps.
        # This is necessary because, while yellow flags slow the field considerably, some drivers still put in laps on occasion that
        #   are fast enough to not be filtered by the outlier limit, but are still affected by the slowing event.
        dfr['lap_validity'] = True
        dfr.loc[(dfr['lap_seconds'] >= dfr['valid_lap_threshold']) | (dfr['lap_seconds'].isnull()), 'lap_validity'] = False
        dfvs = dfr.groupby(['session_key', 'lap_number']).agg({'lap_validity': 'sum'})
        dfvs['field_valid_lap'] = dfvs['lap_validity'] > 10
        dfvs = dfvs['field_valid_lap']
        dfr = dfr.merge(dfvs, on=['session_key', 'lap_number'])

        # We now have two columns on df for checking whether a lap is valid:
        # if 'field_valid_lap' is False, something caused over 10 drivers to have a slow lap, so drop it
        #   (this driver may have had an acceptable time, but it's probably slower than normal due to the event and should be filtered)
        # if 'lap_validity' is False, automatically drop the lap
        #   (something specific to this driver caused them to have a slow lap, but it may not have affected any other cars)
        dfr = dfr.loc[(dfr['lap_validity'] == True) & (dfr['field_valid_lap'] == True)]

        #Drop any lap that's a pit out lap automatically, it will be slower (but may not get detected by lap_validity) and not reflect real race times.
        dfr = dfr.loc[dfr['is_pit_out_lap'] != True]

        return dfr

    def normalize_lap_times(self, df):
        """
        Function attempting to normalize lap times, accounting for fuel consumption/weight, and lap length.
        :param df: df of lap times
        :return: ndf: new dataframe with additional column 'normalized_lap_seconds'
        """
        # Okay. It doesn't seem possible to estimate how much fuel loss affects times based on lap times alone. There are too many other factors affecting lap times.
        # The standard assumption is 110 kg of fuel spent linearly over the course of the lap, at a cost of .3 seconds/10kg of fuel.
        # All races are roughly the same length (around 305-310 km, 44-80 laps, 57 average), meaning fuel efficiency is likely around 2.8 km/kg, and each kg costs about .03 seconds
        # So for each race, we should:
        # Find the remaining fuel in kg in the car for a given lap (normalizing the amount based on the half lap fuel number), multiply that by .03 seconds/kg,
        # subtract the result from the recorded lap time. We subtract because we're calculating the chunk of extra seconds of lap time due to the fuel weight. We get this formula->
        #   lap_time - (110 - (((110 / total_s_laps) * (lap_number - .5))) * .03)) = adjusted time.

        ndf = df.copy()
        ndf['normalized_lap_seconds'] = ndf['lap_seconds'] - ((110 - ((110 / ndf['total_session_laps']) * (ndf['lap_number'] - .5))) * .03)

        # Now we have normalized lap times. But can we go further?
        # Let's try to normalize all lap times based on the average lap time.
        # Basically, lets get the average lap time for a session for a driver, then for each lap calculate a percentage based on the lap time compared to the average.
        # So if the average lap time for a session-driver is 100s, and the current lap time is 90s, then the normalized percentage would be ((90 - 100)/100) * 100 = -10%.
        # Similarly, if the average time for a different race is 80s and the current lap time is 90s, we get a percentage of 12.5%.
        # Now instead of seeing two identical 90s laps, we can see that the first lap is actually "faster" as a percentage difference from the average (-10% vs 12.5%).

        ndfg = ndf.groupby(['session_key', 'driver_name']).agg({'normalized_lap_seconds':'mean'}).rename(columns={'normalized_lap_seconds': 'average_normalized_lap_seconds'})
        ndf = ndf.merge(ndfg, on=['session_key', 'driver_name'])
        #Keep in mind that a smaller ratio is "faster". Also helpful to remember that the closer to 1 a ratio is, the closer to the average time it is.
        ndf['lap_time_percentage_compared_to_average'] = round(((ndf['normalized_lap_seconds'] - ndf['average_normalized_lap_seconds']) / ndf['average_normalized_lap_seconds']) * 100, 2)

        return ndf


    def analyze_stint_df(self, full_df):
        """
        Function to analyze stint and compound combinations and build a new df of the data.
        :param full_df: full combined df of laps & stints
        :return: dataframe grouped by stint and compound with extra analysis columns
        """
        # General static tire analysis (how many times each is used, average stint length, common stints for compound), laps/times are not used or considered.
        ldf = (full_df.groupby(['track_name', 'driver_name', 'stint_number'])
               .agg({'stint_length' : (lambda x: x.value_counts().index[0]),
                     'session_key': (lambda x: x.value_counts().index[0]),
                     'compound' : (lambda x: x.value_counts().index[0])}))

        colorMap = {'HARD': 'ghostwhite', 'MEDIUM': 'gold', 'SOFT': 'firebrick', 'INTERMEDIATE': 'seagreen', 'WET': 'royalblue'}

        cdf = ldf.groupby('compound').agg({'stint_length': 'sum', 'session_key': 'count'}).rename(columns={'session_key': 'compound_stint_count', 'stint_length': 'compound_laps'})
        cdf['average_compound_laps'] = cdf['compound_laps'] / cdf['compound_stint_count']
        cdf['color'] = pd.Series(colorMap)

        sdf = ldf.groupby('stint_number').agg({'session_key':'count', 'stint_length':'mean'}).rename(columns={'session_key':'stint_count', 'stint_length':'avg_stint_length'})
        def get_final_stint_count(x):
            i = x.name
            if i >= len(sdf):
                return x['stint_count']
            return x['stint_count'] - sdf.loc[i + 1, 'stint_count']
        sdf['final_stint_count'] = sdf.apply(get_final_stint_count, axis=1)


        scdf = ldf.groupby(['stint_number', 'compound']).agg({'stint_length': 'sum', 'session_key': 'count'}).rename(columns={'session_key': 'compound_count_per_stint', 'stint_length': 'compound_stint_laps'})
        scdf['average_compound_length_for_this_stint'] = scdf['compound_stint_laps']/scdf['compound_count_per_stint']

        return scdf, cdf, sdf