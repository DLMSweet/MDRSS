# pylint: disable=line-too-long
import logging
import json
from uuid import UUID
from redis import StrictRedis
import requests
from feedgen.feed import FeedGenerator
from pprint import pprint

module_logger = logging.getLogger('mdapi')
REDIS = StrictRedis(host="localhost", decode_responses=True)

def cache(func):
    def wrapper(*args, **kwargs):
        if REDIS.exists(str(kwargs['request_uri'])):
            module_logger.debug("Got {} from cache".format(kwargs['request_uri']))
            return json.loads(REDIS.get(str(kwargs['request_uri'])))
        response = func(*args, **kwargs)
        if response:
            REDIS.setex(str(kwargs['request_uri']), 300, json.dumps(response))
            module_logger.debug("Put {} into cache with 5m TTL".format(kwargs['request_uri']))
        return response
    return wrapper

def cache_id(func):
    def wrapper(*args, **kwargs):
        if REDIS.exists(str(args[1])):
            module_logger.warn("Got {} from cache".format(str(args[1])))
            return UUID(REDIS.get(str(args[1])))
        response = func(*args, **kwargs)
        if response:
            REDIS.setex(str(args[1]), 3600, str(response))
            module_logger.warn("Put {} into cache with 60m TTL".format(str(args[1])))
        return response
    return wrapper

class RSSFeed():
    """
    A basic class to handle the Mangadex API as a RSS feed
    Just returns the last 10 results. You want more? Go to the site.
    """
    def __init__(self, api_url):
        """
        Herp derp I'm an init function
        """
        self.logger = logging.getLogger('mdapi.rss')
        self.api_url = api_url

    def generate_feed(self, manga_id, language_filter=["en"]):
        if isinstance(manga_id, int):
            self.manga_id = self.convert_legacy_id(manga_id)
        chapters = self.get_recent_chapters(manga_id, language_filter)
        manga = self.get_manga(manga_id)
        if manga is None or chapters is None:
            return None
        fg = FeedGenerator()
        fg.id(manga["data"]["attributes"]["title"]["en"])
        fg.title(manga["data"]["attributes"]["title"]["en"])
        fg.link(href="https://magmadex.org/{}/rss".format(manga_id))
        fg.description(manga["data"]["attributes"]["description"]["en"])
        
        for chapter in chapters["results"]:
            fe = fg.add_entry()
            fe.id("https://magmadex.org/reader/{}".format(chapter["data"]["id"]))
            fe.published(chapter["data"]["attributes"]["publishAt"])
            fe.updated(chapter["data"]["attributes"]["updatedAt"])
            fe.link(href="https://magmadex.org/reader/{}".format(chapter["data"]["id"]))
            title_desc = "{} - Chapter {}".format(manga["data"]["attributes"]["title"]["en"], chapter["data"]["attributes"]["chapter"])
            if chapter["data"]["attributes"]["title"]:
                title_desc = title_desc + " | {}".format(chapter["data"]["attributes"]["title"])
            fe.title(title_desc)
            fe.description(title_desc)
        return fg.rss_str(pretty=True)

    @cache
    def make_request(self, request_uri=None):
        """
        Class to handle making requests to the MD API, rate limited
        """
        try:
            response = requests.get('{}/{}'.format(self.api_url, request_uri))
            if response.ok:
                try:
                    return response.json()
                except json.decoder.JSONDecodeError:
                    self.logger.warn("Failed to get valid response for {}".format(request_uri))
            elif response.status_code == 429:
                # Rate limited.
                self.logger.error("Being ratelimited by the API, please slow down")
            else:
                # Response wasn't okay
                self.logger.warn("Something went wrong: {}".format(response.status_code))
        except requests.exceptions.ConnectionError:
            self.logger.warn("Failed to connect to {}".format(self.api_url))
        return None

    def get_manga(self, manga_id):
        """
        Let's get a Manga
        """
        if isinstance(manga_id, int):
            manga_id = self.convert_legacy_id(manga_id)
        return self.make_request(request_uri='manga/{}'.format(manga_id))

    def get_recent_chapters(self, manga_id, language_filter):
        """
        Grab chapters for the Manga
        """
        if isinstance(manga_id, int):
            manga_id = self.convert_legacy_id(manga_id)
        locale_filter = "&".join(["locales[]={}".format(x) for x in language_filter])
        return self.make_request(request_uri='manga/{}/feed?order[chapter]=desc&{}'.format(manga_id, locale_filter))


    @cache_id
    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        new_uuid = requests.post('{}/legacy/mapping'.format(self.api_url), data=payload).json()[0]["data"]["attributes"]["newId"]
        self.logger.debug("Converted legacy ID {} to new UUID {}".format(manga_id, new_uuid))
        return UUID(new_uuid)
