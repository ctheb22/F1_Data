import streamlit as st
import altair as alt
import pandas as pd

from data_import import DataUtility
from data_formatter import DataFormatter

di = DataUtility()
dc = DataFormatter()

masterdf = di.get_all_laps_and_sessions_per_year_df(2023)
stint_compound_df, compound_df, stint_df = dc.analyze_stint_df(masterdf)
master_lapdf = dc.normalize_lap_times(dc.remove_invalid_lap_times(masterdf))

altair_color_dict = {'HARD': 'white', 'MEDIUM': 'gold', 'SOFT': 'firebrick', 'INTERMEDIATE': 'seagreen', 'WET': 'royalblue'}
streamlit_color_dict = {'HARD': '#ffffff', 'MEDIUM': '#f3d61e', 'SOFT': '#fc3c30', 'INTERMEDIATE': '#368a35', 'WET': '#2458e3'}
stint_color_list = ['#DAF7A6', '#FFC300', '#FF5733', '#C70039', '#900C3F', '#581845', '#4f2d44', '#392532', '#161215']
colTitles = ['HARD', 'MEDIUM', 'SOFT', 'WET/INT']
compoundOrder = {'HARD':0, 'MEDIUM':1, 'SOFT':2, 'INTERMEDIATE':3, 'WET':4}

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

    # We get a temporarily filtered masterdf to perform stint/compound based calculations, but we drop it
    # and don't use it for lap times for reasons outlined below.
    tempdf = filter_master_df(masterdf, driver_filter, track_filter)
    stint_compound_df, compound_df, stint_df= dc.analyze_stint_df(tempdf)

    # We filter master_lapdf rather than recalculating with the filtered masterdf because that will throw off some of our
    # data cleaning, and probably allow laps into the data that we don't actually want.
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
st.dataframe(pivot_compound_vs_stint[sorted(pivot_compound_vs_stint.columns, key=compoundOrder.get)])

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
    return round(df.loc[cf & sf, 'normalized_lap_seconds'].mean(), 2) if not df.loc[cf & sf].empty else 'NA'

def generate_pie_chart(df, value_col, cat_col, color_dict):
    pie = (
        alt.Chart(df.reset_index())
        .mark_arc()
        .encode(
            theta=alt.Theta(field=value_col, type='quantitative'),
            color=alt.Color(field=cat_col).scale(domain=color_dict.keys(),
                                                    range=color_dict.values()),
            order=alt.Order(field=value_col, sort='ascending')
        )
    )
    st.altair_chart(pie, use_container_width=True)

def generate_bar_chart(df, x, y, x_label, y_label):
    bar = (
        alt.Chart(df.reset_index())
        .mark_bar()
        .encode(
            x=alt.X(x, sort='-y').title(x_label),
            y=alt.Y(y).title(y_label),
            color=alt.Color("color", legend=None).scale(None)
        )
        .interactive()
    )
    st.altair_chart(bar, use_container_width=True)

def generate_value_columns(df, func, col_titles=colTitles):
    cols = st.columns(len(col_titles))
    for i in range(len(col_titles)):
        with (cols[i]):
            if col_titles[i] == 'WET/INT':
                val = func(df, 'WET') + func(df, 'INTERMEDIATE')
            else:
                val = func(df, col_titles[i])
            st.metric(label=col_titles[i], value=val)

st.header("Analysis / COMPOUND:")

############### Display Pie chart of all stint usages. ###############
st.subheader('Number of times compound was used')
generate_pie_chart(compound_df, 'compound_stint_count', 'compound', altair_color_dict)
generate_value_columns(pivot_compound_vs_stint, compound_sum)

############### Number of laps run / compound chart ###############
st.subheader('Number of laps run per compound')
generate_pie_chart(compound_df, 'compound_laps', 'compound', altair_color_dict)
generate_value_columns(compound_df, compound_lap_count)


############### Average life in laps / compound chart ###############
st.subheader('Average Laps/Compound')
generate_bar_chart(compound_df, 'compound', 'average_compound_laps', 'Compound', 'Laps')
generate_value_columns(compound_df, average_compound_laps)

############### Times/lap number per stint. ###############
# Example: how fast on average is the first lap of a hard stint.
st.subheader('Average lap speeds for given compounds (minus wet/int):')
generate_value_columns(lapdf, get_avg_lap_times, col_titles=colTitles[:3])

#Filter df.
# tldf = lapdf.loc[~lapdf['compound'].isin(['WET', 'INTERMEDIATE'])]
# pivot_percent_vs_compound = pd.pivot_table(tldf, values='lap_time_percentage_compared_to_average', index='lap_in_stint', columns=['compound'], aggfunc="mean")
# pivot_seconds_vs_compound = pd.pivot_table(tldf, values='normalized_lap_seconds', index='lap_in_stint', columns=['compound'], aggfunc="mean")
#
# #Generate the color list from the compounds that exist.
# streamlit_colors = [streamlit_color_dict[col] for col in pivot_seconds_vs_compound.columns]
# st.line_chart(data=pivot_percent_vs_compound, color=streamlit_colors)
# st.line_chart(data=pivot_seconds_vs_compound, color=streamlit_colors)

st.subheader("During which stints was each compound used?")
st.bar_chart(pivot_compound_vs_stint.T, stack=False, color=stint_color_list[:len(pivot_compound_vs_stint.index)])


st.header("Analysis / STINT:")
st.subheader('How often was each compound used for a given stint?')
#Populates the altair color list with colors for compounds that exist in our filtered data.
altair_color_list = [streamlit_color_dict[compound] for compound in pivot_compound_vs_stint.columns]
st.bar_chart(pivot_compound_vs_stint, stack=False, color=altair_color_list)

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

st.subheader('Stats per stint:')
s1col, s2col, s3col, s4col = st.columns(4)
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

st.text('''* Lap times have been filtered and adjusted in an attempt to normalize them over 
the course of a standard length race: This includes cutting out extreme outliers,
and attempting to remove any laps that may have been artificially slowed (yellow flag, 
pit out laps, standing starts, etc...). Lap times have also been adjusted to attempt 
to account for weight loss due to fuel consumption assuming a (probably overly) simple
linear relationship.''')
