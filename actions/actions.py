from typing import Any, Text, Dict, List, Union, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet, AllSlotsReset, FollowupAction
from rasa_sdk.types import DomainDict
from rasa_sdk.executor import CollectingDispatcher
import pandas as pd
from fuzzywuzzy import fuzz
import math
from geopy.geocoders import Nominatim


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


class ActionGetCity(Action):

    def name(self) -> Text:
        return "action_get_city"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        country = tracker.latest_message['entities'][0].get('value')

        dispatcher.utter_message(text="What city would you like to search?"
                                      "\n Government spelling and title of city for best results. ")
        return [SlotSet("country", country)]


class ActionGetCategory(Action):

    def name(self) -> Text:
        return "action_get_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        city = tracker.latest_message['entities'][0].get('value')

        dispatcher.utter_message(text="Please type the organization/category/keyword" 
                                      " of the service you are looking for."
                                      "\n Examples would include 'baby clothes', 'hatzala', 'shul',"
                                      " 'bikor cholim', 'Israel, 'gemach for simcha', 'school'"
                                      " 'baby', 'religious', 'funeral', 'wedding',  etc. "
                                      "\n please limit response to as few words as possible for best results.")

        return [SlotSet("city", city)]


class ActionChesedMatch(Action):

    def name(self) -> Text:
        return "action_chesed_match"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            country = tracker.get_slot('country')
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
            else:
                response = f'I searched for {category} near {location} and this is what I found: '

                num_matches = 0
                if len(chesed_matches_t1) != 0:
                    chesed_matches_t1_sorted = sorted(chesed_matches_t1, key=lambda x: x[1])

                    for match in chesed_matches_t1_sorted:
                        row = country_df.iloc[match[0]]
                        response += f'\n \n' \
                                    f' \n * Name: {row["name"]} *' \
                                    f' \n Phone Number: {row["phone_number"]}' \
                                    f' \n About: {row["quote"]}' \
                                    f' \n Link: {row["full_filename"]}'

                        num_matches += 1
                        if num_matches == 4:
                            break

                if len(chesed_matches_t2) != 0:
                    chesed_matches_t2_sorted = sorted(chesed_matches_t2, key=lambda x: x[1])

                    if num_matches == 4:
                        pass
                    else:
                        for match in chesed_matches_t2_sorted:
                            row = country_df.iloc[match[0]]
                            response += f'\n \n' \
                                        f' \n * Name: {row["name"]} *' \
                                        f' \n Phone Number: {row["phone_number"]}' \
                                        f' \n About: {row["quote"]}' \
                                        f' \n Link: {row["full_filename"]}'
                            num_matches += 1
                            if num_matches == 4:
                                break

                response += "\n \n" \
                            "Not able to find what you are looking for?" \
                            "\n Get in touch directly with one our our case managers: text +1 (833) 424-3733 on Whatsapp." \
                            "\n  If you ever need this service again, just say 'hi'!"

        except Exception as e:
            response = 'Sorry, an error has occurred, please try your request again with different' \
                       ' location (or fix spelling) ' \
                       'and keyword. If this message persists, please contact: ' \
                       '+1 (833) 424-3733 on Whatsapp to let us know. '

        dispatcher.utter_message(text=response)

        return [AllSlotsReset()]
