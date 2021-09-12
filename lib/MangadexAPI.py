# pylint: disable=line-too-long
# pylint: disable=logging-format-interpolation
# pylint: disable=missing-module-docstring
import logging
import time
import json
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from redis import StrictRedis
import requests
from lib.rcache import DistributedCache as rcache
from lib.ratelimit import RateLimitDecorator as ratelimit
from lib.ratelimit import RateLimitException, sleep_and_retry
from lib.Manga import Manga

logging.basicConfig(filename='/tmp/tmdfe.log', format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
module_logger = logging.getLogger('mdapi')
REDIS = StrictRedis(host="localhost", decode_responses=True)

class APIError(Exception):
    """
    There was an error getting information from the API
    """

class APIRateLimit(Exception):
    """
    We're trying to hit the API too fast
    """

class MangaNotFound(Exception):
    """
    Manga wasn't found bro
    """

class MangadexAPI():
    """
    A basic class to handle the Mangadex API
    """
    def __init__(self, api_url):
        """
        Does very little. Just holds the API url
        """
        self.logger = logging.getLogger('mdapi.api')
        self.api_url = api_url

    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        response = self.make_request('legacy/mapping', payload=payload, req_type="POST")
        try:
            new_uuid = response["data"][0]["attributes"]["newId"]
            self.logger.debug("Converted legacy ID {} to new UUID {}".format(manga_id, new_uuid))
            return UUID(new_uuid)
        except json.decoder.JSONDecodeError:
            self.logger.warning("Failed to get new UUID for {} - {}".format(manga_id, response))
        except AttributeError:
            self.logger.warning("Failed to get new UUID for {} - {}".format(manga_id, response))
        return None

    def get_manga(self, manga_id):
        """
        Returns a Manga based on it's UUID
        """
        if isinstance(manga_id, int):
            try:
                manga_id = self.convert_legacy_id(manga_id)
            except MangaNotFound:
                return None
        return Manga(manga_id, api=self)

    def search_manga(self, title, offset=0):
        """
        Returns search results or None if nothing is found
        """
        results = self.make_request('manga?title={}&offset={}'.format(title, offset))
        return_results = []
        try:
            if results["data"]:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_manga = {executor.submit(Manga, x["id"], api=self): x for x in results['data']}
                    for future in as_completed(future_to_manga):
                        manga = future_to_manga[future] # pylint: disable=unused-variable
                        try:
                            manga_cl = future.result()
                        except Exception as exc:
                            print('Generated an exception: {}'.format(exc))
                        else:
                            return_results.append(manga_cl)
                return (results["total"], return_results)
        except TypeError:
            self.logger.debug("No results found for {}".format(title))
        return (0, None)

    @rcache
    @sleep_and_retry
    @ratelimit(calls=5, period=1)
    def make_request(self, request_uri, payload=None, req_type="GET"):
        """
        Class to handle making requests to the MD API, rate limited
        """
        try:
            self.logger.warning("UNCACHED: Calling API with: {}".format(request_uri))
            if req_type == "POST":
                response = requests.post('{}/{}'.format(self.api_url, request_uri), data=payload)
            else:
                response = requests.get('{}/{}'.format(self.api_url, request_uri))
            if response.status_code == 204:
                return None
            if response.ok:
                try:
                    return response.json()
                except json.decoder.JSONDecodeError as invalid_response:
                    raise APIError("Failed to get valid response for {}".format(request_uri)) from invalid_response
            elif response.status_code == 429:
                self.logger.error("Being ratelimited by the API, please slow down")
                raise RateLimitException(response.status_code, 1) 
            else:
                # Response wasn't okay
                self.logger.error('{}/{}'.format(self.api_url, request_uri))
                raise APIError(response.status_code)
        except requests.exceptions.ConnectionError as connection_error:
            raise APIError("Failed to connect to {}".format(self.api_url)) from connection_error
        return None

