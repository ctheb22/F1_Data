import streamlit as st
import pandas as pd

from Source.data_import import DataUtility
from Source.data_cleaner import DataCleaner

di = DataUtility()
dc = DataCleaner()

masterdf = di.get_all_laps_and_sessions_per_year_df(2023)
stint_compound_df, compound_df, stint_df = dc.analyze_stint_df(masterdf)
master_lapdf = dc.normalize_lap_times(dc.remove_invalid_lap_times(masterdf))

def filter_df(driver_filter='', track_filter=''):
    """
    Update the global dataframes we use to display data, filtering them according to user input.
    :param driver_filter: list of driver names to filter by.
    :param track_filter: list of track names to filter by.
    :return: nothing.
    """
    global stint_compound_df, lapdf, compound_df, stint_df

    def filter_master_df(master, dfilter, tfilter):
        return_df = master.loc[master['driver_name'].isin(dfilter)] if dfilter else master.copy()
        return_df = return_df.loc[return_df['track_name'].isin(tfilter)] if tfilter else return_df
        return return_df

    tempdf = filter_master_df(masterdf, driver_filter, track_filter)
    stint_compound_df, compound_df, stint_df= dc.analyze_stint_df(tempdf)
    lapdf = filter_master_df(master_lapdf, driver_filter, track_filter)

st.title("F1 2023 SEASON:")
st.header("TIRE COMPOUND & STINT ANALYSIS")

dcol, tcol = st.columns(2)
with dcol:
    driver_options = st.multiselect(
        "Filter by driver(s)",
        masterdf['driver_name'].unique(),
    )

with tcol:
    track_options = st.multiselect(
        "Filter by track(s)",
        masterdf['track_name'].unique(),
    )

filter_df(driver_filter=driver_options, track_filter=track_options)
pivot_compound_vs_stint = pd.pivot_table(stint_compound_df, values='compound_count_per_stint', index='stint_number', columns=['compound'], aggfunc="sum")

compound_color_dict = {'HARD': '#E9E9E9', 'MEDIUM': '#E9E926', 'SOFT': '#FF483F', 'INTERMEDIATE': '#44C266', 'WET': '#426AB9'}
stint_color_list = ['#DAF7A6', '#FFC300', '#FF5733', '#C70039', '#900C3F', '#581845', '#4f2d44', '#392532', '#161215']

colorList = []
for compound in pivot_compound_vs_stint.columns:
        colorList.append(compound_color_dict[compound])

def get_compound_col(df, compound='', col=''):
    if compound and col:
        return df.loc[compound, col] if compound in df.index else 0
    return 0

def compound_lap_count(df, compound=''):
    return int(get_compound_col(df, compound, 'compound_laps'))

def average_compound_laps(df, compound=''):
    return round(get_compound_col(df, compound, 'average_compound_laps'), 2)

def compound_sum(df, compound=''):
    if compound:
        return int(df[compound].sum()) if compound in df.columns else 0
    return 0

def get_avg_lap_times(df, compound='', stint='', addl_stints=False):
    cf = df['compound'] == compound if compound else True
    if not addl_stints:
        sf = df['stint_number'] == int(stint) if stint else True
    else:
        sf = df['stint_number'] >= int(stint) if stint else True
    return round(df.loc[cf & sf, 'lap_seconds'].mean(), 2) if not df.loc[cf & sf].empty else 'NA'

st.header("Analysis / COMPOUND:")
htcol, mtcol, stcol, wtcol = st.columns(4)
with htcol:
    st.subheader("HARD:")
    st.metric(label="Times Tires Used:", value=compound_sum(pivot_compound_vs_stint, 'HARD'))
    st.metric(label="Total Laps Run:", value=compound_lap_count(compound_df, 'HARD'))
    st.metric(label="Average Life (Laps):", value=average_compound_laps(compound_df, 'HARD'))
    st.metric(label='*Avg Lap Time (s):', value=get_avg_lap_times(lapdf, compound='HARD'))
with mtcol:
    st.subheader("MEDIUM:")
    st.metric(label="Times Tires Used:", value=compound_sum(pivot_compound_vs_stint, 'MEDIUM'))
    st.metric(label="Total Laps Run:", value=compound_lap_count(compound_df, 'MEDIUM'))
    st.metric(label="Average Life (Laps):", value=average_compound_laps(compound_df, 'MEDIUM'))
    st.metric(label='*Avg Lap Time (s):', value=get_avg_lap_times(lapdf, compound='MEDIUM'))
with stcol:
    st.subheader("SOFT:")
    st.metric(label="Times Tires Used:", value=compound_sum(pivot_compound_vs_stint, 'SOFT'))
    st.metric(label="Total Laps Run:", value=compound_lap_count(compound_df, 'SOFT'))
    st.metric(label="Average Life (Laps):", value=average_compound_laps(compound_df, 'SOFT'))
    st.metric(label='*Avg Lap Time (s):', value=get_avg_lap_times(lapdf, compound='SOFT'))
with wtcol:
    st.subheader("WET/INT:")
    w_stint_sum = compound_sum(pivot_compound_vs_stint, 'WET') + compound_sum(pivot_compound_vs_stint, 'INTERMEDIATE')
    w_lap_sum = compound_lap_count(compound_df, 'WET') + compound_lap_count(compound_df, 'INTERMEDIATE')
    w_avg_lap_sum = average_compound_laps(compound_df, 'WET') + average_compound_laps(compound_df, 'INTERMEDIATE')
    st.metric(label="Times Tires Used:", value=w_stint_sum)
    st.metric(label="Total Laps Run:", value=w_lap_sum)
    st.metric(label="Average Life (Laps):", value=w_avg_lap_sum)
    st.metric(label='*Avg Lap Time (s):', value='Na')

st.subheader("During which stints was each compound used?")
st.bar_chart(pivot_compound_vs_stint.T, stack=False, color=stint_color_list[:len(pivot_compound_vs_stint.index)])

st.header("Analysis / STINT:")
s1col, s2col, s3col, s4col = st.columns(4)

def avg_stint_laps(df, stint=0, avg_remaining=False):
    if stint != 0:
        if not avg_remaining:
            return round(df.loc[stint, 'avg_stint_length'], 2) if stint in df.index else 'NA'
        else:
            return round(df.loc[stint:, 'avg_stint_length'].mean(), 2) if stint in df.index else 'NA'
    return 'NA'

def final_stint_count(df, stint=0, sum_remaining=False):
    if stint != 0:
        if not sum_remaining:
            return round(df.loc[stint, 'final_stint_count'], 2) if stint in df.index else 'NA'
        else:
            return round(df.loc[stint:, 'final_stint_count'].sum(), 2) if stint in df.index else 'NA'
    return 'NA'

with s1col:
    st.subheader("1ST:")
    st.metric(label="Avg Length (Laps):", value=avg_stint_laps(stint_df, 1))
    st.metric(label="Final Stint Count:", value=final_stint_count(stint_df, 1))
    st.metric(label="*Avg Lap Time (s):", value=get_avg_lap_times(lapdf, stint='1'))
with s2col:
    st.subheader("2nd:")
    st.metric(label="Avg Length (Laps):", value=avg_stint_laps(stint_df, 2))
    st.metric(label="Final Stint Count:", value=final_stint_count(stint_df, 2))
    st.metric(label="*Avg Lap Time (s):", value=get_avg_lap_times(lapdf, stint='2'))
with s3col:
    st.subheader("3rd:")
    st.metric(label="Avg Length (Laps):", value=avg_stint_laps(stint_df, 3))
    st.metric(label="Final Stint Count:", value=final_stint_count(stint_df, 3))
    st.metric(label="*Avg Lap Time (s):", value=get_avg_lap_times(lapdf, stint='3'))
with s4col:
    st.subheader("4th and Up:")
    st.metric(label="Avg Length (Laps):", value=avg_stint_laps(stint_df, 4, avg_remaining=True))
    st.metric(label="Final Stint Count:", value=final_stint_count(stint_df, 4, sum_remaining=True))
    st.metric(label="*Avg Lap Time (s):", value=get_avg_lap_times(lapdf, stint='4', addl_stints=True))
st.subheader('How often was each compound used for a given stint?')
st.bar_chart(pivot_compound_vs_stint, stack=False, color=colorList)
st.text('''* Lap times have been filtered and adjusted in an attempt to normalize them over 
the course of a standard length race: This includes cutting out extreme outliers,
and attempting to remove any laps that may have been artificially slowed (yellow flag, 
pit out laps, standing starts, etc...). Lap times have also been adjusted to attempt 
to account for weight loss due to fuel consumption assuming a (probably overly) simple
linear relationship.''')
