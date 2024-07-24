"""
This is an example web scraper for booking.com used in scrapfly blog article:
https://scrapfly.io/blog/how-to-scrape-bookingcom/

To run this scraper set env variable $SCRAPFLY_KEY with your scrapfly API key:
$ export $SCRAPFLY_KEY="your key from https://scrapfly.io/dashboard"

For example use instructions see ./run.py
"""
import json
import re
import os
from collections import defaultdict
from typing import Dict, List, Optional, TypedDict
from urllib.parse import urlencode
from uuid import uuid4
import asyncio

# from loguru import logger as log
from datetime import datetime, timedelta
from scrapfly import ScrapeApiResponse, ScrapeConfig, ScrapflyClient

RETRIEVE_QUERY_PATH = os.path.join("data", "queries", "retrieve_body.graphql")
SCRAPE_QUERY_PATH = os.path.join("data", "queries", "scrape_hotel.graphql")
SCRAPFLY = ScrapflyClient(key="scp-live-9f23777855724dec804e73230baffc63")
BASE_CONFIG = {
    # Booking.com requires Anti Scraping Protection bypass feature:
    "asp": True,
    "country": "US",
}

class ScrapflyCacheException(Exception):
    "scrapfly cache cannot be used with sessions when scraping hotel data"


class Location(TypedDict):
    """Location dict"""
    b_max_los_data: dict
    b_show_entire_homes_checkbox: bool
    cc1: str
    cjk: bool
    dest_id: str
    dest_type: str
    label: str
    label1: str
    label2: str
    labels: list
    latitude: float
    lc: str
    longitude: float
    nr_homes: int
    nr_hotels: int
    nr_hotels_25: int
    photo_uri: str
    roundtrip: str
    rtl: bool
    value: str


class LocationSuggestions(TypedDict):
    """Location result dict"""
    results: List[Location]


async def search_location_suggestions(query: str) -> LocationSuggestions:
    """scrape booking.com location suggestions to find location details for search scraping"""
    result = await SCRAPFLY.async_scrape(
        ScrapeConfig(
            url="https://accommodations.booking.com/autocomplete.json",
            method="POST",
            headers={
                "Origin": "https://www.booking.com",
                "Referer": "https://www.booking.com/",
                "Content-Type": "text/plain;charset=UTF-8",
            },
            body=f'{{"query":"{query}","pageview_id":"","aid":800210,"language":"en-us","size":5}}',
        )
    )
    data = json.loads(result.content)
    return data


def retrieve_graphql_body(result: ScrapeApiResponse) -> List[Dict]:
    """parse the graphql search query from the HTML and return the full graphql body"""
    selector = result.selector
    script_data = selector.xpath("//script[@data-capla-store-data='apollo']/text()").get()
    json_script_data = json.loads(script_data)
    keys_list = list(json_script_data["ROOT_QUERY"]["searchQueries"].keys())
    second_key = keys_list[1]
    search_query_string = second_key[len("search("):-1]
    input_json_object = json.loads(search_query_string)
    return {
        "operationName": "FullSearch",
        "variables": {
            "input": input_json_object["input"],
            "carouselLowCodeExp": False
        },
        "extensions": {},
        "query": open(RETRIEVE_QUERY_PATH, "r", encoding="utf-8").read()
    }


def generate_graphql_request(url_params: str, body: Dict, offset: int):
    """create a scrape config for the search graphql request"""
    body["variables"]["input"]["pagination"]["offset"] = offset
    return ScrapeConfig(
        "https://www.booking.com/dml/graphql?" + url_params,
            headers={
                "accept":"*/*",
                "cache-control":"no-cache",
                "content-type": "application/json",
                "origin":"https://www.booking.com",
                "pragma":"no-cache",
                "priority":"u=1, i",
                "referer":"https://www.booking.com/searchresults.en-gb.html?" + url_params,
            },
        body=body,
        method="POST"
    )


def parse_graphql_response(response: ScrapeApiResponse) -> List[Dict]:
    """parse the search results from the graphql response"""
    data = json.loads(response.content)
    parsed_data = data["data"]["searchQueries"]["search"]["results"]
    return parsed_data


async def scrape_search(
    query,
    checkin: str = "",  # e.g. 2023-05-30
    checkout: str = "",  # e.g. 2023-06-26
    number_of_rooms=1,
    max_pages: Optional[int] = None,
) -> List[Dict]:
    """Scrape booking.com search"""
    #log.info(f"scraping search for {query} {checkin}-{checkout}")
    # first we must find destination details from provided query
    # for that scrape suggestions from booking.com autocomplete and take the first one
    location_suggestions = await search_location_suggestions(query)
    destination = location_suggestions["results"][0]
    url_params = urlencode(
        {
            "ss": destination["value"],
            "ssne": destination["value"],
            "ssne_untouched": destination["value"],
            "checkin": checkin,
            "checkout": checkout,
            "no_rooms": number_of_rooms,
            "dest_id": destination["dest_id"],
            "dest_type": destination["dest_type"],
            "efdco": 1,
            "group_adults": 1,
            "group_children": 0,
            "lang": "en-gb",
            "sb": 1,
            "sb_travel_purpose": "leisure",
            "src": "index",
            "src_elem": "sb",
        }
    )
    search_url = "https://www.booking.com/searchresults.en-gb.html?" + url_params
    # first scrape the first page and find total amount of pages
    first_page = await SCRAPFLY.async_scrape(ScrapeConfig(search_url, **BASE_CONFIG))
    _total_results = int(
        first_page.selector.css("h1").re(r"([\d,]+) properties found")[0].replace(",", "")
    )
    _max_scrape_results = max_pages * 25
    if _max_scrape_results and _max_scrape_results < _total_results:
        _total_results = _max_scrape_results

    data = []
    to_scrape = [
        generate_graphql_request(
            url_params,
            retrieve_graphql_body(first_page),
            offset
        ) for offset in range(0, _total_results, 25)
    ]
    #log.info(f"scraping search results from the graphql api: {len(to_scrape)} pages to request")
    async for response in SCRAPFLY.concurrent_scrape(to_scrape):
        data.extend(parse_graphql_response(response))
    #log.success(f"scraped {len(data)} results from search pages")
    return data


class PriceData(TypedDict):
    """Stores prices and availability"""
    checkin: str
    min_length_of_stay: int
    avg_price_pretty: str
    available: int
    avg_price_raw: float
    length_of_stay: int
    price_pretty: str
    price: float


class Hotel(TypedDict):
    """Stores Hotel information (i.e address, description)"""
    url: str
    id: str
    description: str
    address: str
    images: List[str]
    lat: str
    lng: str
    features: Dict[str, List[str]]
    price: List[PriceData]
    rooms: List[str]


async def parse_hotel(result: ScrapeApiResponse) -> Hotel:
    """Parses hotel info"""
    #log.debug("parsing hotel page: {}", result.context["url"])
    sel = result.selector

    hotel_features_xpath = '//div[@data-testid="property-section--content"]/div[2]/div'
    features = defaultdict(list)
    for box in sel.xpath(hotel_features_xpath):
        if "Quarto Triplo" in str(box):
            print("Presente")
        type_ = box.xpath('.//span[contains(@data-testid, "facility-group-icon")]/../text()').get()
        feats = [f.strip() for f in box.css("li ::text").getall() if f.strip()]
        features[type_] = feats

    room_info_xpath = '//div[@id="maxotelRoomArea"]/section[@class="roomstable"]/div[position()>1]'
    rooms = defaultdict(list)
    for box in sel.xpath(room_info_xpath):
        room = box.xpath('.//a/span/text()').get()
        max_people = box.xpath('.//@aria-label').get()
        beds = box.xpath('.//span[contains(text(), "bed")]/text()').getall()
        rooms[room] = {
        'max_people': max_people,
        'beds': beds
        }

    def transform_selector(selector, sep=""):
        return sep.join(sel.css(selector).getall()).strip()

    lat, lng = sel.css(".show_map_hp_link::attr(data-atlas-latlng)").get("0,0").split(",")
    return {
        "url": result.context["url"],
        "id": re.findall(r"b_hotel_id:\s*'(.+?)'", result.content)[0],
        "title": sel.css("h2::text").get(),
        "description": transform_selector("div#property_description_content ::text", "\n"),
        "address": transform_selector(".hp_address_subtitle::text"),
        "images": sel.css("a.bh-photo-grid-item>img::attr(src)").getall(),
        "lat": lat,
        "lng": lng,
        "features": dict(features),
        "rooms": rooms
    }


async def scrape_hotel(url: str, checkin: str, price_n_days=61) -> Hotel:
    """
    Scrape Booking.com hotel data and pricing information.
    """
    # first scrape hotel info details
    # note: we are using scrapfly session here as both info and pricing requests
    #       have to be from the same IP address/session
    if BASE_CONFIG.get("cache"):
        raise ScrapflyCacheException()
    #log.info(f"scraping hotel {url} {checkin} with {price_n_days} days of pricing data")
    session = str(uuid4()).replace("-", "")
    result = await SCRAPFLY.async_scrape(
        ScrapeConfig(
            url,
            session=session,
            **BASE_CONFIG,
        )
    )
    hotel = await parse_hotel(result)

    # To scrape price we'll be calling Booking.com's graphql service
    # in particular we'll be calling AvailabilityCalendar query
    # first, extract hotel variables:
    _hotel_country = re.findall(r'hotelCountry:\s*"(.+?)"', result.content)[0]
    _hotel_name = re.findall(r'hotelName:\s*"(.+?)"', result.content)[0]
    _csrf_token = re.findall(r"b_csrf_token:\s*'(.+?)'", result.content)[0]

    with open(SCRAPE_QUERY_PATH, "r", encoding="utf-8") as f:
        scrape_query = f.read()
    # then create graphql query
    gql_body = json.dumps(
        {
            "operationName": "AvailabilityCalendar",
            # hotel varialbes go here
            # you can adjust number of adults, room number etc.
            "variables": {
                "input": {
                    "travelPurpose": 2,
                    "pagenameDetails": {
                        "countryCode": _hotel_country,
                        "pagename": _hotel_name,
                    },
                    "searchConfig": {
                        "searchConfigDate": {
                            "startDate": checkin,
                            "amountOfDays": price_n_days,
                        },
                        "nbAdults": 2,
                        "nbRooms": 1,
                    },
                }
            },
            "extensions": {},
            # this is the query itself, don't alter it
            "query": scrape_query,
        },
        # note: this removes unnecessary whitespace in JSON output
        separators=(",", ":"),
    )
    # scrape booking graphql
    result_price = await SCRAPFLY.async_scrape(
        ScrapeConfig(
            "https://www.booking.com/dml/graphql?lang=en-gb",
            method="POST",
            body=gql_body,
            session=session,
            # note that we need to set headers to avoid being blocked
            headers={
                "content-type": "application/json",
                "x-booking-csrf-token": _csrf_token,
                "referer": result.context["url"],
                "origin": "https://www.booking.com",
            },
            **BASE_CONFIG,
        )
    )
    price_data = json.loads(result_price.content)
    hotel["price"] = price_data["data"]["availabilityCalendar"]["days"]
    return hotel


async def main():
    """Testing scraper"""
    days_to_scrape_prices = 7

    booking_hotel_dict = await scrape_hotel(
        "https://www.booking.com/hotel/br/porto-de-galinhas-alto-padrao.pt-br.html",
        checkin=(
            datetime.now() + timedelta(days=days_to_scrape_prices)
        ).strftime('%Y-%m-%d'), # One week from now
        price_n_days=days_to_scrape_prices,
    )

    print(booking_hotel_dict)

if __name__ == "__main__":
    asyncio.run(main())
