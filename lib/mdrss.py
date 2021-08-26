# pylint: disable=line-too-long
# pylint: disable=logging-format-interpolation
# pylint: disable=missing-module-docstring
import logging
import json
import time
from uuid import UUID
import requests
from feedgen.feed import FeedGenerator
from lib.rcache import DistributedCache as rcache
# You only really need this to prevent hitting the backend too often
from lib.ratelimit import RateLimitDecorator as ratelimit
from lib.ratelimit import sleep_and_retry

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

    def generate_feed(self, manga_id, language_filter=["en"], feedtype="rss"):
        if isinstance(manga_id, int):
            manga_id = self.convert_legacy_id(manga_id)
        if manga_id is None:
            return None
        chapters = self.get_recent_chapters(manga_id, language_filter)
        manga = self.get_manga(manga_id)
        if manga is None or chapters is None:
            return None
        feed = FeedGenerator()
        feed.id(manga["data"]["attributes"]["title"]["en"])
        feed.title(manga["data"]["attributes"]["title"]["en"])
        feed.link(href="https://mangadex.org/title/{}".format(manga_id))
        feed.link(href="https://mangadex.org/title/{}".format(manga_id), rel="self")
        if manga["data"]["attributes"]["description"]["en"]:
            feed.description(manga["data"]["attributes"]["description"]["en"])
        else:
            feed.description("No Content")

        for chapter in chapters["results"]:
            feed_entry = feed.add_entry()
            feed_entry.id("https://mangadex.org/chapter/{}".format(chapter["data"]["id"]))
            feed_entry.published(chapter["data"]["attributes"]["publishAt"])
            feed_entry.updated(chapter["data"]["attributes"]["updatedAt"])
            feed_entry.link(href="https://mangadex.org/chapter/{}".format(chapter["data"]["id"]))

            title_desc = "{} - Chapter {}".format(manga["data"]["attributes"]["title"]["en"], chapter["data"]["attributes"]["chapter"])
            if chapter["data"]["attributes"]["title"]:
                title_desc = title_desc + " | {}".format(chapter["data"]["attributes"]["title"])
            feed_entry.title(title_desc)
            feed_entry.description(title_desc)
        if feedtype == "atom":
            return feed.atom_str(pretty=True)
        return feed.rss_str(pretty=True)

    @rcache
    @sleep_and_retry
    @ratelimit(calls=5, period=1)
    def make_request(self, request_uri, payload=None, req_type="GET"):
        """
        Class to handle making requests to the MD API, rate limited
        """
        while True:
            try:
                if req_type == "POST":
                    response = requests.post('{}/{}'.format(self.api_url, request_uri), data=payload)
                else:
                    response = requests.get('{}/{}'.format(self.api_url, request_uri))
                if response.status_code == 204:
                    return None
                if response.ok:
                    try:
                        return response.json()
                    except json.decoder.JSONDecodeError:
                        self.logger.warning("Failed to get valid response for {}".format(request_uri))
                elif response.status_code == 429:
                    # Rate limited.
                    self.logger.error("Being ratelimited by the API, waiting for a second...")
                else:
                    # Response wasn't okay
                    self.logger.warning("Something went wrong: {}".format(response.status_code))
                    return None
            except requests.exceptions.ConnectionError:
                self.logger.warning("Failed to connect to {}".format(self.api_url))
                return None
            time.sleep(1)
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
        locale_filter = "&".join(["translatedLanguage[]={}".format(x) for x in language_filter])
        return self.make_request('manga/{}/feed?order[chapter]=desc&{}'.format(manga_id, locale_filter))


    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        response = self.make_request('legacy/mapping', payload=payload, req_type="POST")
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
