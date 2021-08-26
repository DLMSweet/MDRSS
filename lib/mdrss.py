# pylint: disable=line-too-long
import logging
import json
import time
from uuid import UUID
import requests
from feedgen.feed import FeedGenerator
from lib.rcache import DistributedCache as rcache
from lib.ratelimit import RateLimitDecorator as ratelimit
from lib.ratelimit import RateLimitException, sleep_and_retry

module_logger = logging.getLogger('mdapi')

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

    def generate_feed(self, manga_id, language_filter=["en"], type="rss"):
        if isinstance(manga_id, int):
            manga_id = self.convert_legacy_id(manga_id)
        if manga_id is None:
            return None
        chapters = self.get_recent_chapters(manga_id, language_filter)
        manga = self.get_manga(manga_id)
        if manga is None or chapters is None:
            return None
        fg = FeedGenerator()
        fg.id(manga["data"]["attributes"]["title"]["en"])
        fg.title(manga["data"]["attributes"]["title"]["en"])
        fg.link(href="https://magmadex.org/manga/{}".format(manga_id))
        fg.link(href="https://magmadex.org/rss/manga/{}".format(manga_id), rel="self")
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
        if type == "atom":
            return fg.atom_str(pretty=True)
        return fg.rss_str(pretty=True)

    @rcache
    @sleep_and_retry
    @ratelimit(calls=5, period=1)
    def make_request(self, request_uri, payload=None, type="GET"):
        """
        Class to handle making requests to the MD API, rate limited
        """
        while True:
            try:
                if type == "POST":
                    response = requests.post('{}/{}'.format(self.api_url, request_uri), data=payload)
                else:
                    response = requests.get('{}/{}'.format(self.api_url, request_uri))
                if response.ok:
                    try:
                        return response.json()
                    except json.decoder.JSONDecodeError:
                        self.logger.warn("Failed to get valid response for {}".format(request_uri))
                elif response.status_code == 429:
                    # Rate limited.
                    self.logger.error("Being ratelimited by the API, waiting for a second...")
					time.sleep(1)
                else:
                    # Response wasn't okay
                    self.logger.warn("Something went wrong: {}".format(response.status_code))
                    return None
            except requests.exceptions.ConnectionError:
                self.logger.warn("Failed to connect to {}".format(self.api_url))
                return None
        return None

    def get_manga(self, manga_id):
        """
        Let's get a Manga
        """
        return self.make_request('manga/{}'.format(manga_id))

    def get_recent_chapters(self, manga_id, language_filter):
        """
        Grab chapters for the Manga
        """
        locale_filter = "&".join(["locales[]={}".format(x) for x in language_filter])
        return self.make_request('manga/{}/feed?order[chapter]=desc&{}'.format(manga_id, locale_filter))


    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        response = self.make_request('legacy/mapping', payload=payload, type="POST")
        try:
            new_uuid = response[0]["data"]["attributes"]["newId"]
            self.logger.debug("Converted legacy ID {} to new UUID {}".format(manga_id, new_uuid))
            return UUID(new_uuid)
        except json.decoder.JSONDecodeError:
            self.logger.warning("Failed to get new UUID for {} - {}".format(manga_id, response))
        except AttributeError:
            self.logger.warning("Failed to get new UUID for {} - {}".format(manga_id, response))
        return None

    def __str__(self):
        return "<RSSFeed>"