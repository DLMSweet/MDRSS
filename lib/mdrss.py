# pylint: disable=line-too-long
import logging
import json
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

    def generate_feed(self, manga_id):
        chapters = self.get_recent_chapters(manga_id)
        manga = self.get_manga(manga_id)
        fg = FeedGenerator()
        fg.id(manga["data"]["attributes"]["title"]["en"])
        fg.title(manga["data"]["attributes"]["title"]["en"])
        fg.link(href="https://magmadex.org/{}/rss".format(manga_id))
        fg.description(manga["data"]["attributes"]["description"]["en"])
        
        for chapter in chapters["results"]:
            fe = fg.add_entry()
            fe.id("https://magmadex.org/reader/{}".format(chapter["data"]["id"]))
            fe.title(chapter["data"]["attributes"]["title"])
            fe.published(chapter["data"]["attributes"]["publishAt"])
            fe.updated(chapter["data"]["attributes"]["updatedAt"])
            fe.link(href="https://magmadex.org/reader/{}".format(chapter["data"]["id"]))
            fe.description(chapter["data"]["attributes"]["title"])
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
        return self.make_request(request_uri='manga/{}'.format(manga_id))

    def get_recent_chapters(self, manga_id):
        """
        Grab chapters for the Manga
        """
        return self.make_request(request_uri='chapter?manga={}&order[updatedAt]=asc'.format(manga_id))
