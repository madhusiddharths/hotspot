import numpy as np
import pandas as pd
import json
import plotly.express as px
import os
import dash
from dash import dcc, html, callback, Input, Output, State
import dash.dependencies as dd
from datetime import datetime, timedelta
import re
import geopandas as gpd
import requests
from opencage.geocoder import OpenCageGeocode
import warnings
import dash_bootstrap_components as dbc


geojson_dir = 'geojson'

# Combine all individual GeoJSON files into one GeoJSON object
all_geojson = {
    "type": "FeatureCollection",
    "features": []
}

# Iterate over each file in the directory and add to the combined GeoJSON
for filename in os.listdir(geojson_dir):
    if filename.endswith('.geojson'):
        with open(os.path.join(geojson_dir, filename)) as f:
            geojson_data = json.load(f)
            all_geojson['features'].extend(geojson_data['features'])

def get_semantics(data):
    semantics = []
    for i in data['semanticSegments']:
        if 'timelinePath' in i.keys():
            continue
        elif 'visit' in i.keys():
            temp_dict = {'start':i['startTime'],
                         'end':i['endTime'],
                         'lat':i['visit']['topCandidate']['placeLocation']['latLng'].split(',')[0].replace('°', ''),
                         'long':i['visit']['topCandidate']['placeLocation']['latLng'].split(',')[1].replace('°', ''),
                         'type':'stay'}
            semantics.append(temp_dict)
        elif 'activity' in i.keys():
            temp_dict = {'start':i['startTime'],
                         'end':i['endTime'],
                         'activity':i['activity']['topCandidate']['type'],
                         'start_lat':i['activity']['start']['latLng'].split(',')[0].replace('°', ''),
                         'end_lat':i['activity']['end']['latLng'].split(',')[0].replace('°', ''),
                         'start_long':i['activity']['start']['latLng'].split(',')[1].replace('°', ''),
                         'end_long':i['activity']['end']['latLng'].split(',')[1].replace('°', ''),
                         'type':'travel'}
            semantics.append(temp_dict)
        else:
            print(i)
            break
    return semantics

def get_raw(data):
    raw = []
    for i in data['rawSignals']:
        if 'activityRecord' in i.keys():
            temp_dict = {'activity':i['activityRecord']['probableActivities'][0]['type'],
                         'timestamp':i['activityRecord']['timestamp'],
                         'type':'travel'}
            raw.append(temp_dict)
        elif 'wifiScan' in i.keys():
            temp_dict = {'timestamp':i['wifiScan']['deliveryTime'],
                         'type':'wifiscan'}
            raw.append(temp_dict)
        elif 'position' in i.keys():
            temp_dict = {'timestamp':i['position']['timestamp'],
                         'lat':i['position']['LatLng'].split(',')[0].replace('°', ''),
                         'long':i['position']['LatLng'].split(',')[1].replace('°', ''),
                         'type':'positionscan'}
            raw.append(temp_dict)
        else:
            print(i)
            break
    return raw

from datetime import datetime

def get_latest(raw, semantics, start_time, end_time):
    start_time = datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    end_time = datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f%z')

    updated_raw_start_index = len(raw)  # Default to all entries
    updated_raw_end_index = -1  # Default to no entries
    updated_semantics_start_index = len(semantics)  # Default to all entries
    updated_semantics_end_index = -1  # Default to no entries

    # Calculate start index for raw
    for i in range(len(raw)):
        if datetime.strptime(raw[i]['timestamp'], '%Y-%m-%dT%H:%M:%S.%f%z') >= start_time:
            updated_raw_start_index = i
            break

    # Calculate start index for semantics
    for i in range(len(semantics)):
        if datetime.strptime(semantics[i]['start'], '%Y-%m-%dT%H:%M:%S.%f%z') >= start_time:
            updated_semantics_start_index = i
            break

    # Calculate end index for raw
    for i in range(len(raw) - 1, -1, -1):  # Adjusted to include index 0
        if datetime.strptime(raw[i]['timestamp'], '%Y-%m-%dT%H:%M:%S.%f%z') <= end_time:
            updated_raw_end_index = i - 1
            break

    # Calculate end index for semantics
    for i in range(len(semantics) - 1, -1, -1):  # Adjusted to include index 0
        if datetime.strptime(semantics[i]['start'], '%Y-%m-%dT%H:%M:%S.%f%z') <= end_time:
            updated_semantics_end_index = i - 1
            break

    # Return slices, handling cases where no valid indices were found
    raw_result = raw[updated_raw_start_index:updated_raw_end_index + 1] if updated_raw_end_index >= 0 else []
    semantics_result = semantics[updated_semantics_start_index:updated_semantics_end_index + 1] if updated_semantics_end_index >= 0 else []
    
    return raw_result, semantics_result

def get_activity_location(updated_raw, updated_semantics):
    time_activity = []
    n = 0
    for i in range(len(updated_semantics)):
        for j in range(n,len(updated_raw),1):
            if datetime.strptime(updated_raw[j]['timestamp'], '%Y-%m-%dT%H:%M:%S.%f%z') >= datetime.strptime(updated_semantics[i]['start'], '%Y-%m-%dT%H:%M:%S.%f%z') and datetime.strptime(updated_raw[j]['timestamp'], '%Y-%m-%dT%H:%M:%S.%f%z') <= datetime.strptime(updated_semantics[i]['end'], '%Y-%m-%dT%H:%M:%S.%f%z'):
                time_activity.append((j,i)) # (updated_raw, updated_semantics)
                n = n + 1
    return time_activity


def get_zip_code_activity(updated_raw, updated_semantics, location_activity):
    n = 1
    zip_activity = []
    flag = 0
    for i in location_activity:
        print(n)
        n = n + 1
        if len(updated_raw[i[0]].keys()) == 4: # position scan
            temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                         'type':updated_raw[i[0]]['type'],
                         'zipcode':get_zip_code(updated_raw[i[0]]['lat'],updated_raw[i[0]]['long'])}
            zip_activity.append(temp_dict)
        elif len(updated_raw[i[0]].keys()) == 2: # wifi scan
            if len(updated_semantics[i[1]]) == 5:
                temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                             'type':updated_raw[i[0]]['type'],
                             'zipcode':get_zip_code(updated_semantics[i[1]]['lat'],updated_semantics[i[1]]['long'])}
                zip_activity.append(temp_dict)
            else:
                if flag == 0:
                    temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                                 'type':updated_raw[i[0]]['type'],
                                 'zipcode':get_zip_code(updated_semantics[i[1]]['start_lat'],updated_semantics[i[1]]['start_long'])}
                    flag = 1
                    zip_activity.append(temp_dict)
                else:
                    temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                                 'type':updated_raw[i[0]]['type'],
                                 'zipcode':get_zip_code(updated_semantics[i[1]]['end_lat'],updated_semantics[i[1]]['end_long'])}
                    flag = 0
                    zip_activity.append(temp_dict)
        elif len(updated_raw[i[0]].keys()) == 3: # activity record
            if len(updated_semantics[i[1]]) == 5:
                temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                             'type':updated_raw[i[0]]['activity'],
                             'zipcode':get_zip_code(updated_semantics[i[1]]['lat'],updated_semantics[i[1]]['long'])}
                zip_activity.append(temp_dict)
            else:
                if flag == 0:
                    temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                                 'type':updated_raw[i[0]]['activity'],
                                 'zipcode':get_zip_code(updated_semantics[i[1]]['start_lat'],updated_semantics[i[1]]['start_long'])}
                    flag = 1
                    zip_activity.append(temp_dict)
                else:
                    temp_dict = {'timestamp':updated_raw[i[0]]['timestamp'],
                                 'type':updated_raw[i[0]]['activity'],
                                 'zipcode':get_zip_code(updated_semantics[i[1]]['end_lat'],updated_semantics[i[1]]['end_long'])}
                    flag = 0
                    zip_activity.append(temp_dict)
    return zip_activity

def get_zip_code(lat, lon):
    key = '50275e53501449ea92d343426825408d'
    geocoder = OpenCageGeocode(key)
    
    results = geocoder.reverse_geocode(lat, lon)
    
    if results and 'postcode' in results[0]['components']:
        zip_code = results[0]['components']['postcode']
        return zip_code
    else:
        return None

# run this when you need new data
# with open('Timeline (1).json', 'r') as file:
#     data = json.load(file)
# semantics = get_semantics(data)
# raw = get_raw(data)
# updated_raw, updated_semantics = get_latest(raw, semantics, '2024-09-18T00:00:00.000-05:00', '2024-09-25T00:00:00.000-05:00')
# location_activity = get_activity_location(updated_raw, updated_semantics)
# zip_activity = get_zip_code_activity(updated_raw, updated_semantics, location_activity)
# with open('data_18_24.json', 'w') as json_file:
#     json.dump(zip_activity, json_file, indent=4)
def run_app_2(server):
    df = pd.read_csv('Influenza_Surveillance_Weekly.csv')
    df['WEEK_START'] = pd.to_datetime(df['WEEK_START'])
    df['WEEK_END'] = pd.to_datetime(df['WEEK_END'])
    df = df[df['WEEK_START'].dt.year >= 2024]
    df.sort_values(by='WEEK_START', ascending = False, inplace = True)
    df.drop(['MMWR_WEEK'], axis = 1, inplace = True)
    df['week'] = np.arange(37, 1, -1)

    df1 = pd.read_csv('risk_level.csv')
    df1 = df1[(df1['ZIP_Code'] > 60600) & (df1['ZIP_Code'] < 60666)]
    df1 = df1[pd.to_datetime(df1['Week_Start']).dt.year >= 2024]
    df1['Week_Start'] = pd.to_datetime(df1['Week_Start'])
    df1['Week_End'] = pd.to_datetime(df1['Week_End'])
    df1.rename(columns={'ILI_Activity_Level':'ILI'}, inplace = True) # ili - influenza like illness
    df1.sort_values(by='Week_Start', inplace = True)

    age_df = pd.read_csv('FluSurveillance_Custom_Download_Data.csv',skiprows = 2)
    age_df.rename(columns=str.lower, inplace=True)
    age_df = age_df[['age category','mmwr-year','mmwr-week','cumulative rate','weekly rate']]
    age_df.replace([np.inf, -np.inf], np.nan, inplace=True)
    age_df.dropna(inplace = True)
    age_df['mmwr-year'] = age_df['mmwr-year'].astype('int64')
    age_df['mmwr-week'] = age_df['mmwr-week'].astype('int64')
    age_df = age_df[age_df['mmwr-year'] == 2024]
    age_df = age_df[~(age_df['age category'] == 'Overall')]

    population = pd.read_csv('Chicago_Population_Counts.csv')
    population = population[population['Year'] == 2021]
    population = population[['Geography','Population - Total']]
    total_population = population.iloc[0]
    population.drop(index = 175, axis = 0, inplace = True)
    population['Geography'] = population['Geography'].astype('int64')
    pop_dict = population.set_index('Geography')['Population - Total'].to_dict()

    with open('data_18_24.json', 'r') as file:
        json_data = json.load(file)
    df2 = pd.DataFrame(json_data)
    df2['timestamp'] = pd.to_datetime(df2['timestamp'])
    df2['type'] = df2['type'].astype('str')
    df2['zipcode'] = df2['zipcode'].astype('int64')
    df2 = df2[~((df2['timestamp'].duplicated()) & ((df2['type'] == 'positionscan') | (df2['type'] == 'wifiscan')))]
    df2['week'] = df2['timestamp'].dt.isocalendar().week
    df2 = df2[df2['zipcode'] <= 60666]
    df2.dropna(inplace = True)
    df2['population'] = df2['zipcode'].apply(lambda x : pop_dict[x])
    temp_df = df[['week','LAB_FLU_TESTED']]
    temp_df.loc[:,'week'] = temp_df['week'] + 2
    temp_df_dict = temp_df.set_index('week')['LAB_FLU_TESTED'].to_dict()
    df2['cases'] = df2['week'].apply(lambda x : temp_df_dict[x])
    df2.reset_index(drop = True, inplace = True)
    list_df = list(df2.values)

    i = 0
    while i < len(list_df) - 1:
        if list_df[i+1][1] == list_df[i][1] and list_df[i+1][2] == list_df[i][2]:
            list_df.pop(i+1)
        else:
            i += 1

    estimate = []
    estimate_daterange = {}
    factors = {'UNKNOWN':1.0,'positionscan':2.0,'wifiscan':2.0,'STILL':2.0,'WALKING':1.0,'ON_FOOT':1.0,'RUNNING':0.5,'ON_BICYCLE':0.5, 'IN_ROAD_VECHICLE':0.5,
                'IN_RAIL_VEHICLE':5.0,'IN_VEHICLE':2.0, 'TILTING':1.0,'EXITING_VEHICLE':1.0}
    for i in range(len(list_df)-1):
        if list_df[i][0].day == list_df[i+1][0].day:
            temp = ((list_df[i+1][0] - list_df[i][0]).total_seconds() / 60, factors[list_df[i][1]], list_df[i][5]/list_df[i][4])
            if sum(temp) > 240:
                continue
            estimate.append(temp)
        else:
            temp_date_holder = datetime.strptime(str(list_df[i][0]), '%Y-%m-%d %H:%M:%S%z').strftime('%Y-%m-%d')
            estimate_daterange[temp_date_holder] = i
    
    app2 = dash.Dash("app2", external_stylesheets=[dbc.themes.BOOTSTRAP], server=server, url_base_pathname='/app2/')
    app2.layout = html.Div([
        # Date Picker for selecting the date range
        html.Div([
            html.Div(
                dcc.Link(
                    html.H6(
                        "back",
                        style = {
                            "height":'47px', 
                            'width':'100px',
                            'backgroundColor':'black',
                            'color':'white',
                            'text-decoration':'none',
                            'textAlign':'center',
                            "padding": "10px"},
                    ),
                    href='/app1/',
                    style={'text-decoration': 'none'},
                ),
                style = {'text-decoration':'none',}
            ),
            dcc.DatePickerSingle(
                id='date-picker',
                date=datetime(2024, 8, 10),
            ),
            dcc.Dropdown(
                id='disease-dropdown',
                options=[
                    {'label': 'Flu', 'value': 'flu'},
                    {'label': 'Covid - 19', 'value': 'covid'},
                    {'label': 'Respiratory Syncytial Virus', 'value': 'rsv'},
                    {'label': 'Hay Fever', 'value': 'hayfever'},
                    {'label': 'Norovirus', 'value': 'norovirus'},
                    {'label': 'Lyme Disease', 'value' : 'lyme'},
                    {'label': 'All', 'value': 'All'}  # Option for "All"
                ],
                value='flu',  # Default value
                clearable=False,  # Prevent clearing the selection
                style={'width': '300px', 'height':'47px','borderRadius':'0px',},
            ),
            dcc.Dropdown(
                id='city-dropdown',
                options=[
                    {'label': 'Chicago', 'value': 'Chicago'},
                    {'label': 'New York', 'value': 'New York'},
                    {'label': 'Los Angeles', 'value': 'Los Angeles'},
                    {'label': 'Houston', 'value': 'Houston'},
                    {'label': 'Phoenix', 'value': 'Phoenix'},
                    {'label': 'All', 'value': 'All'}  # Option for "All"
                ],
                value='Chicago',  # Default value
                clearable=False,  # Prevent clearing the selection
                style={'width': '300px', 'height':'47px','borderRadius':'0px',},
            ),
            
        ], style = {
            'display':'flex',
            'flexDirection':'row',
            'justifyContent':'space-between',
            'gap': '10px',
            'paddingLeft':'2%',
            'paddingRight':'2%',
        }),

        # Add some space between the date picker and the map
        html.Div(style={'height': '20px'}),  # Space between components

        # Use a flexbox container to ensure both map and data boxes align well
        html.Div([
            # Div to wrap the map and limit its width
            html.Div([
                dcc.Graph(id='choropleth-map')
            ], style={
                'width': '60%',  # Increased map width to 60%
                'height': 'calc(100vh - 100px)',  # Adjust height calculation
                'padding': '10px',
            }),

            # div to display the left half of the chart
            html.Div([
                # Div to display the ili value and pct change in the first row
                html.Div([
                    # Div for ili value
                    html.Div([
                        # Blue Box around the texts
                        html.Div([
                            # ILI value (large text)
                            html.Div(id='ili-value-60616', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("ILI Value", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#2E8B57',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    }, id = 'ili_value_box'),
        
                    # Div for pct change
                    html.Div([
                        # Blue Box around the texts
                        html.Div([
                            # Pct_change value (large text)
                            html.Div(id='pct_change', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("Pct_change", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#5F9EA0',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    }, id = 'pct_change_box',)
                ], style = {
                    'display': 'flex',
                    'flexDirection':'row',
                    'width':'100%',
                }),

                # div for cases weekly and targetted age group
                html.Div([
                    # Div to display cases_weekly and targetted age group side by side
                    html.Div([
                        # cases weekly box
                        html.Div([
                            # value large text
                            html.Div(id='cases_weekly', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("Weekly cases", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#4682B4',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    }, id='weekly_cases_box',),
        
                    # Div for targetted age group
                    html.Div([
                        html.Div([
                            # value (large text)
                            html.Div(id = 'targetted_age', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("targetted age", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#8A2BE2',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    },id='targetted_age_box',)
                ], style = {
                    'display': 'flex',
                    'flexDirection':'row',
                    'width':'100%',
                }),
                
                # div for probability of infection and empty box
                html.Div([
                    # Div to display probability and empty group side by side
                    html.Div([
                        # probability box
                        html.Div([
                            # value large text
                            html.Div(id = 'probability', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("Probability", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#20B2AA',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    }, id='probability_box',),
        
                    # Div for empty group
                    html.Div([
                        html.Div([
                            # value (large text)
                            html.Div('0.6 %', style={
                                'fontSize': '50px',  # Increased font size
                                'textAlign': 'center',
                                'color': 'white',
                            }),
                            # Label text (smaller text)
                            html.Div("Vaccination", style={
                                'fontSize': '20px', 
                                'color': 'white', 
                                'textAlign': 'center',
                            }),
                        ], style={
                            'display': 'flex',
                            'flexDirection': 'column',  # Ensure texts are one below the other
                            'justifyContent': 'center',
                            'alignItems': 'center',
                            'width': '250px',
                            'height': '100px',
                            'borderRadius': '10px',
                            'backgroundColor': '#6495ED',  # Set the background color to blue
                            'margin': '10px',  # Reduced margin for spacing
                        }),
                    ], style={
                        'display': 'flex', 
                        'flexDirection': 'column', 
                        'alignItems': 'center',
                        'width': '50%',
                        'padding': '10px',  # Add padding for spacing
                    }, id = 'vaccination_box',)
                ], style = {
                    'display': 'flex',
                    'flexDirection':'row',
                    'width':'100%',
                }),
                
            ], style={
                'display':'flex',
                'flexDirection':'column',
            }),
        ], style={
            'display': 'flex', 
            'flexDirection': 'row',  # Horizontal alignment
            'justifyContent': 'space-between',  # Space between map and boxes
            'width': '100%', 
            'height': 'calc(100vh - 100px)',  # Adjust height
        }),
        dbc.Tooltip(
            '''Influenza Like Illniess for current zipcode. ILI percentage for each ZIP Code for the week is compared to the mean ILI percentage during 
            the non-influenza months (summer months). Level 1 corresponds to an ILI percentage below the mean, level 2 to an 
            ILI percentage less than one standard deviation (SD) above the mean, level 3 to an ILI percentage more than one, but 
            less than two SDs above mean, and so on, with level 10 corresponding to an ILI percentage more than eight SDs above the mean''',
            target="ili_value_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
        dbc.Tooltip(
            "Percentage change in cases from the previous week (current week is the last week from the data picker)",
            target="pct_change_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
        dbc.Tooltip(
            "Total number of new cases this week (current week is the last week from the date picker)",
            target="weekly_cases_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
        dbc.Tooltip(
            "The most targetted age group for the disease. Its based on infection rate per 100,000 people",
            target="targetted_age_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
        dbc.Tooltip(
            "Probability that you can contract the disease based on your time line data. Its considers the zipcodes (weight adjusted), mode of transportation (weight adjusted), and duration of stay",
            target="probability_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
        dbc.Tooltip(
            "The overall vaccination rate of chicago",
            target="vaccination_box",  # The ID of the element to attach the tooltip to
            placement="top",  # Where the tooltip will appear
            trigger="hover"  # Show tooltip on click (you can change this to 'hover' or 'focus' as needed)
        ),
    ], style = {
        'display':'flex',
        'flexDirection':'column',
        'marginTop':'2%',
    })


    @app2.callback(
        [Output('choropleth-map', 'figure'),
        Output('ili-value-60616', 'children'),
        Output('pct_change','children'),
        Output('cases_weekly','children'),
        Output('targetted_age','children'),
        Output('probability','children'),],
        [
            Input('date-picker', 'date'),
        ]
    )

    def update_map(date):
        # populate the graph
        week_number = pd.to_datetime(date).isocalendar().week
        filtered_data = df1[df1['MMWR_Week'] == week_number]
        fig = px.choropleth_mapbox(filtered_data, 
                                geojson=all_geojson, 
                                locations='ZIP_Code', 
                                featureidkey="properties.postal-code",  # Match the key in your GeoJSON
                                color='ILI',
                                color_continuous_scale="Viridis",
                                range_color=(1, 10),  # Normalized range
                                mapbox_style="carto-positron",
                                zoom=9, center={"lat": 41.85, "lon": -87.6298},  # Center on Chicago
                                opacity=0.5
                                )
        
        # Update layout to remove margins
        fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})

        # populate the boxes
        if week_number < 40:
            # initialize no values
            ili_display, cases_display, percent_display, age_display, probability_display = 'N/A', 'N/A','N/A','N/A','N/A'
            # populate the ili box
            zip_60616_data = filtered_data[filtered_data['ZIP_Code'] == 60616]
            if not zip_60616_data.empty:
                ili_value_60616 = zip_60616_data['ILI'].iloc[0]
                ili_display = f"{ili_value_60616:.2f}"
            else:
                ili_display = "No Data"

            # populate cases weekly box and pct change box
            if week_number < 38:
                cases_weekly = df[df['week'] == week_number]['LAB_FLU_TESTED'].values[0]
                previous_week_data = df[df['week'] == week_number - 1]
                previous_week_cases = previous_week_data['LAB_FLU_TESTED'].values[0]
                percent_change = ((cases_weekly - previous_week_cases) / previous_week_cases) * 100 if previous_week_cases != 0 else 0
                percent_display = f"{percent_change:.2f}%"
                cases_display = f"{cases_weekly}"  
            else:
                cases_display = "No Data"
                precent_display = "No Data"

            # populate the targetted age box
            if week_number < 39:
                targetted_week = age_df[age_df['mmwr-week'] == week_number]
                targetted_age = age_df.loc[age_df['weekly rate'].idxmax(), 'age category']
                age_display = f"{targetted_age}"
            else:
                age_display = "No Data"

            # popublate the probability box
            if date not in pd.to_datetime(list(estimate_daterange.keys())):
                probability_display = "No Data"
            else:
                end_index = estimate_daterange[date] + 1
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                new_date = date_obj - timedelta(days=1)
                new_date_str = new_date.strftime('%Y-%m-%d')
                start_index = 0
                if new_date_str in estimate_daterange.keys():
                    start_index = estimate_daterange[new_date_str] + 1
                filtered_estimate = estimate[start_index : end_index]
                probability = np.sum(np.prod(filtered_estimate, axis = 1))/600 * 100
                if probability > 99.99:
                    probability = 99.99
                probability_display = f"{probability:.2f}%"

            return fig, ili_display, percent_display, cases_display, age_display, probability_display

        else:
            # If no data for the selected range
            return fig, "No Data", "No Data", "No Data", "No Data", "No Data"

    warnings.filterwarnings("ignore")
    return app2
