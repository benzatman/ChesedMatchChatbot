from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet, AllSlotsReset
from rasa_sdk.executor import CollectingDispatcher
import pandas as pd
from fuzzywuzzy import fuzz
import math
from geopy.geocoders import Nominatim
import re
import requests
from splinter import Browser
import os
import json
from dotenv import load_dotenv


def latLng_dist(lat_start, lng_start, lat_end, lng_end):
    # 3959 for miles 6371 for kilometers
    dist = 3959 * math.acos(
        math.cos(math.radians(lat_start))
        * math.cos(math.radians(lat_end))
        * math.cos(math.radians(lng_end) - math.radians(lng_start))
        + math.sin(math.radians(lat_start))
        * math.sin(math.radians(lat_end))
    )
    return dist


def bitly_url(url):
    load_dotenv()
    token = os.getenv('bitly_access_token')
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    data = { "long_url": url, "domain": "jonec.co", "group_guid": "Bm81gujiye5" }
    data = json.dumps(data)

    response = requests.post('https://api-ssl.bitly.com/v4/shorten', headers=headers, data=data)
    return response.json().get('link')


class ActionGetCity(Action):

    def name(self) -> Text:
        return "action_get_city"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        country = tracker.latest_message['entities'][0].get('value')

        dispatcher.utter_message(text="Which city are you searching for? "
                                      "\nPlease use the official spelling and title of city for best results")
        return [SlotSet("country", country)]


class ActionGetCategory(Action):

    def name(self) -> Text:
        return "action_get_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        city = tracker.latest_message['entities'][0].get('value')

        dispatcher.utter_message(text="Please type the organization/category/keyword" 
                                      " of the service you are looking for.")

        return [SlotSet("city", city)]


class ActionChesedMatch(Action):

    def name(self) -> Text:
        return "action_chesed_match"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            country = tracker.get_slot('country')
            if country == 'USA':
                country = 'US'
            elif country == 'Israel':
                country = 'IL'
            elif country == 'Canada':
                country = 'CA'

            city = tracker.get_slot('city')
            category = tracker.latest_message['entities'][0].get('value')

            geolocator = Nominatim(user_agent='info@justonechesed.org')
            location = geolocator.geocode(city + ' ' + country)
            lat_start = location.latitude
            lng_start = location.longitude

            test_sheet_id_main = '1yf9MjXojfE4HIYct-KlB6H11bCsFSOJ0ecnUvWMJK1s'
            main_sheet_df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{test_sheet_id_main}/export?format=csv&")

            country_df = main_sheet_df[main_sheet_df['country_code'] == country]

            cols_to_search = ['name', 'quote', 'about_me', 'services', 'search_description', 'custom_member_keywords']

            item_category_match_index_t1 = []
            item_category_match_index_t2 = []

            indexer = 0
            for col in cols_to_search:
                if col == 'name':
                    for item in country_df[col]:
                        if fuzz.partial_ratio(category, str(item)) >= 85:
                            if indexer not in item_category_match_index_t1:
                                item_category_match_index_t1.append(indexer)

                        indexer += 1
                else:
                    for item in country_df[col]:
                        if fuzz.partial_ratio(category, str(item)) >= 85:
                            if indexer not in item_category_match_index_t2:
                                item_category_match_index_t2.append(indexer)

                        indexer += 1

                indexer = 0

            num_results = len(item_category_match_index_t1) + len(item_category_match_index_t2)

            chesed_matches_t1 = []
            if len(item_category_match_index_t1) == 0:
                pass
            else:
                for item in item_category_match_index_t1:
                    latLng = [country_df.iloc[item]['Lat'], country_df.iloc[item]['Lon']]
                    lat_end = latLng[0]
                    lng_end = latLng[1]

                    dist = latLng_dist(lat_start, lng_start, lat_end, lng_end)
                    if dist <= 30:
                        chesed_matches_t1.append([item, dist])

            chesed_matches_t2 = []
            if len(item_category_match_index_t2) == 0:
                pass
            else:
                for item in item_category_match_index_t2:
                    latLng = [country_df.iloc[item]['Lat'], country_df.iloc[item]['Lon']]
                    lat_end = latLng[0]
                    lng_end = latLng[1]

                    dist = latLng_dist(lat_start, lng_start, lat_end, lng_end)
                    if dist <= 30:
                        chesed_matches_t2.append([item, dist])

            if len(chesed_matches_t1) == 0 and len(chesed_matches_t2) == 0:
                response = f'Sorry I could not find any results for {category} near {location},' \
                           f' please type "start over" and try a different keyword,' \
                           f' if we got your location wrong, please try another location nearby.'
                matches_remaining = ""
                matches_reported = ""
                num_results = ""
                country = ""
            else:
                response = f'I searched for {category} near {location} and this is what I found: '
                showing = 7
                if num_results < 7:
                    showing = num_results
                response += f'\nShowing {showing} results out of {num_results} matches'

                num_matches = 0
                if len(chesed_matches_t1) != 0:
                    chesed_matches_t1_sorted = sorted(chesed_matches_t1, key=lambda x: x[1])

                    for match in chesed_matches_t1_sorted:
                        row = country_df.iloc[match[0]]

                        response += f'\n \n \n' \
                                    f'\nName: *{row["name"]}*' \
                                    f'\nContact: {row["phone_number"]}' \
                                    f'\nAbout: {row["quote"]}' \
                                    f'\nLink: {bitly_url(row["full_filename"])} \n \n'

                        num_matches += 1
                        if num_matches == 7:
                            break

                if len(chesed_matches_t2) != 0:
                    chesed_matches_t2_sorted = sorted(chesed_matches_t2, key=lambda x: x[1])

                    if num_matches == 7:
                        pass
                    else:
                        for match in chesed_matches_t2_sorted:
                            row = country_df.iloc[match[0]]

                            response += f'\n \n \n' \
                                        f'\nName: *{row["name"]}*' \
                                        f'\nContact: {row["phone_number"]}' \
                                        f'\nAbout: {row["quote"]}' \
                                        f'\nLink: {bitly_url(row["full_filename"])} \n \n'
                            num_matches += 1
                            if num_matches == 7:
                                break

                response += '\n \nHope these help! '

                if num_results > showing:
                    """
                    browser = Browser(driver_name='firefox', headless=True)

                    browser.visit('https://www.chesedmatch.org/search_results?')
                    browser.fill('q', category)
                    browser.fill('location_value', city)
                    button = browser.find_by_id('location_google_maps_homepage')
                    button.click()
                    url = browser.url
                    b_url = bitly_url(url)
                    """
                    b_url = 'https://jonec.co/3CHRuji'

                    response += f"\n \n" \
                                f"*Want more results?* type 'load more' or go to this link: {b_url}"

                if country == "IL":
                    phone_number = '+972 52 377 2881'
                else:
                    phone_number = '+1 (833) 424-3733'
                response += "\n \n" \
                            "Not able to find what you are looking for?" \
                            f"\nGet in touch directory with one of our case managers by WhatsApping {phone_number}."

                while len(response) > 1600:
                    name_locs = [m.start() for m in re.finditer(re.escape('Name'), response)]
                    end_loc = response.find('Hope these help!')
                    resp_p1 = response[:name_locs[-1]]
                    resp_p2 = response[end_loc:]
                    response = resp_p1 + resp_p2
                    showing -= 1

                all_matches = chesed_matches_t1 + chesed_matches_t2
                matches_reported = showing
                matches_remaining = all_matches[showing:]

        except Exception as e:
            response = f'Sorry, an error has occurred, please try your request again with different' \
                       f' location (or fix spelling) ' \
                       f'and keyword. If this message persists, please contact: ' \
                       f'+1 (833) 424-3733 on Whatsapp to let us know and tell us your facing error: {e}. '
            matches_remaining = ""
            matches_reported = ""
            num_results = ""
            country = ""

        dispatcher.utter_message(text=response)

        return [SlotSet('matches_remaining', matches_remaining), SlotSet('matches_reported', matches_reported), SlotSet('num_results', num_results), SlotSet('country', country)]


class ActionLoadMore(Action):

    def name(self) -> Text:
        return "action_load_more"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            matches_remaining = tracker.get_slot('matches_remaining')
            matches_reported = tracker.get_slot('matches_reported')
            num_results = tracker.get_slot('num_results')
            country = tracker.get_slot('country')
            test_sheet_id_main = '1yf9MjXojfE4HIYct-KlB6H11bCsFSOJ0ecnUvWMJK1s'
            main_sheet_df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{test_sheet_id_main}/export?format=csv&")
            country_df = main_sheet_df[main_sheet_df['country_code'] == country]
            showing = 7
            if len(matches_remaining) < 7:
                showing = len(matches_remaining)
            response = f'\nShowing {matches_reported + showing} results out of {num_results} matches'

            for i in range(showing):
                row = country_df.iloc[matches_remaining[i][0]]

                response += f'\n \n \n' \
                            f'\nName: *{row["name"]}*' \
                            f'\nContact: {row["phone_number"]}' \
                            f'\nAbout: {row["quote"]}' \
                            f'\nLink: {bitly_url(row["full_filename"])} \n \n'

            response += '\n \nHope these help! '

            if num_results != (matches_reported + showing):
                b_url = 'https://jonec.co/3CHRuji'

                response += f"\n \n" \
                            f"*Want more results?* type 'load more' or go to this link: {b_url}"

            if country == "IL":
                phone_number = '+972 52 377 2881'
            else:
                phone_number = '+1 (833) 424-3733'

            response += "\n \n" \
                        "Not able to find what you are looking for?" \
                        f"\nGet in touch directory with one of our case managers by WhatsApping {phone_number}."

            while len(response) > 1600:
                name_locs = [m.start() for m in re.finditer('Name', response)]
                end_loc = response.find('Hope these help!')
                resp_p1 = response[:name_locs[-1]]
                resp_p2 = response[end_loc:]
                response = resp_p1 + resp_p2
                showing -= 1

            matches_reported = matches_reported + showing
            matches_remaining = matches_remaining[showing:]

        except Exception as e:
            response = f'Sorry, an error has occurred, please try your request again with different' \
                       f' location (or fix spelling) ' \
                       f'and keyword. If this message persists, please contact: ' \
                       f'+1 (833) 424-3733 on Whatsapp to let us know and tell us your facing error: {e}. '
            matches_remaining = ""
            matches_reported = ""

        dispatcher.utter_message(text=response)

        return [SlotSet('matches_remaining', matches_remaining), SlotSet('matches_reported', matches_reported)]

