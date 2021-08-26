# pylint: disable=line-too-long
import logging
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from redis import StrictRedis
from ratelimit import limits, sleep_and_retry
import requests
import bbcode
from pprint import pprint

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

def lock(lock_name="global_lock"):
    def wrapper(func):
        def inner_wrapper(*args, **kwargs):
            try:
                with REDIS.lock(lock_name, blocking_timeout=5) as lock:
                    results = func(*args, **kwargs)
            except LockError:
                results = None
            return results
        return inner_wrapper
    return wrapper

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

    def get_manga(self, manga_id):
        """
        Returns a Manga based on it's UUID
        """
        return Manga(manga_id, api=self)

    def search_manga(self, title, offset=0):
        """
        Returns search results or None if nothing is found
        """
        results = self.make_request(request_uri='manga?title={}&offset={}'.format(title, offset))
        return_results = []
        if results["results"]:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_manga = {executor.submit(Manga, x["data"]["id"], api=self): x for x in results['results']}
                for future in as_completed(future_to_manga):
                    manga = future_to_manga[future]
                    try:
                        manga_cl = future.result()
                    except Exception as exc:
                        print('Generated an exception: {}'.format(exc))
                    else:
                        return_results.append(manga_cl)
            return (results["total"], return_results)
        return None

    def get_chapter(self, chapter_id):
        """
        Returns a chapter based on it's ID
        """
        chapter = Chapter(api=self)
        try:
            chapter.load_from_uuid(chapter_id)
        except APIError as e:
            self.logger.error("Failed to return chapter: {}".format(e))
            raise
        return chapter

    # Check if it's in the cache, if not proceed. Grab the lock. Check again in case someone updated Cache, proceed.
    @cache
    @lock(lock_name="api_server")
    @cache
    @sleep_and_retry
    @limits(calls=5, period=1)    
    def make_request(self, request_uri=None):
        """
        Class to handle making requests to the MD API, rate limited
        """
        try:
            self.logger.warning("UNCACHED: Calling API with: {}".format(request_uri))
            response = requests.get('{}/{}'.format(self.api_url, request_uri))
            if response.ok:
                try:
                    return response.json()
                except json.decoder.JSONDecodeError:
                    raise APIError("Failed to get valid response for {}".format(request_uri))
            elif response.status_code == 429:
                # Rate limited. Sleep for a second before continuing. TODO: Remove or refactor
                self.logger.error("Being ratelimited by the API, please slow down")
                raise APIRateLimit(response.status_code)
            else:
                # Response wasn't okay
                self.logger.error('{}/{}'.format(self.api_url, request_uri))
                raise APIError(response.status_code)
        except requests.exceptions.ConnectionError:
            raise APIError("Failed to connect to {}".format(self.api_url))
        return None

    async def send_report(self, image_url, success=False, downloaded_bytes=0, duration=0, is_cached=False):
        """
        Sends a report about download speed/success/etc to the backend
        """
        report = json.dumps({ "url": image_url, "success": success, "bytes": downloaded_bytes, "duration": duration, "cached": is_cached })
        resp = requests.post("https://api.mangadex.network/report", data=report)
        if not resp.ok:
            self.logger.info("Failed to report status of image: {} - {}".format(resp.status_code, resp.reason))
            self.logger.debug(resp.json())
            self.logger.debug(report)

class Chapter():
    """
    A Chapter object used to get information about a chapter and
    to pull images for the chapter, including getting a MD@H node
    """
    def __init__(self, manga=None, data=None, api=None):
        """
        Just inits the object, nothing to see here. move along
        """
        self.logger = logging.getLogger('mdapi.chapter')
        self.api = api
        self.data = data
        self.manga = manga
        self.image_server = None
        if self.data:
            self.load_data()

    def load_data(self):
        """
        Copy the data out into attributes to make it easier to
        read without dealing with the JSON object
        """
        try:
            self.chapter_id = self.data["data"]["id"]
            self.chapter = self.data['data']['attributes']['chapter']
            self.volume = self.data['data']['attributes']['volume']
            self.published = self.data['data']['attributes']['publishAt']
            self.created = self.data['data']['attributes']['createdAt']
            self.language = self.data['data']['attributes']['translatedLanguage']
            self.hash = self.data['data']['attributes']['hash']
            self.image_list = self.data['data']['attributes']['data']
            self.manga = [x['id'] for x in self.data['relationships'] if x['type'] == 'manga'][0]
        except KeyError:
            pprint(self.data)
            raise
        except TypeError:
            pprint(self.data['relationships'])
            raise

    def load_from_uuid(self, chapter_id, tries=0):
        """
        Get the chapter information from the API based on the UUID
        """
        response = self.api.make_request(request_uri='chapter/{}'.format(chapter_id))
        self.data = response
        self.load_data()

    @lock(lock_name="image_server")
    def get_image_server(self):
        """
        Attempt to get a MD@H node to pull images from
        """
        if REDIS.exists('at-home/server/{}'.format(self.chapter_id)):
            return json.loads(REDIS.get('at-home/server/{}'.format(self.chapter_id)))["baseUrl"]
        try:
            response = self.api.make_request(request_uri='at-home/server/{}'.format(self.chapter_id))
        except APIRateLimit:
            time.sleep(1)
            return self.get_image_server()
        return response["baseUrl"]


    def get_image_urls(self):
        """
        Get the URLs for the images, in case we want to stick them
        directly into a <img> or pass them to something else
        """
        images = []
        if self.image_server is None:
            self.image_server = self.get_image_server()
        for image in self.image_list:
            images.append("{}/data/{}/{}".format(self.image_server, self.hash, image))
        return images

    async def get_image(self, image, report=True, tries=0):
        """
        Returns an image in a requests Response object
        """
        if tries > 0 or self.image_server is None:
            # Get a new image server
            self.image_server = self.get_image_server()
        if tries > 3:
            # Guess we'll die
            return None
        image_url = "{}/data/{}/{}".format(self.image_server, self.hash, image)
        try:
            data = requests.get(image_url)
        except requests.exceptions.ConnectionError as e:
            self.logger.error("Failed to connect to {} - {}".format(self.image_server, e))
            self.logger.error("Removing failing server from Redis cache")
            REDIS.delete('at-home/server/{}'.format(self.chapter_id))
            if report:
                await self.api.send_report(image_url)
            # Give the system time to breathe. TODO: Remove
            time.sleep(1)
            return await self.get_image(image, report=report, tries=tries+1)
        if data.status_code == 200:
            if report:
                if data.headers['X-Cache'] == "HIT":
                    is_cached = True
                else:
                    is_cached = False
                await self.api.send_report(image_url,
                                 success=True,
                                 downloaded_bytes=len(data.content),
                                 duration=int(data.elapsed.total_seconds()*1000),
                                 is_cached=is_cached)
            return data
        # By default, send a failing report. This doesn't get hit if we had a success above.
        if report:
            await self.api.send_report(image_url)
        return None

    async def get_image_bytes(self, image, tries=0):
        """
        Returns an image as a base64-encoded string
        """
        if tries > 2:
            return None
        image_data = await self.get_image(image)
        if image_data is None:
            return await self.get_image_bytes(image, tries=tries+1)
        content_type = image_data.headers['content-type']
        encoded_image = base64.b64encode(image_data.content).decode('utf-8')
        return "data:{};base64,{}".format(content_type, encoded_image)

    def __str__(self):
        """
        Returns some basic information about the chapter
        """
        return "Volume {}, Chapter {} ({})".format(self.volume, self.chapter, self.language)

class Manga():
    """
    Basic class to handle manga
    """
    def __init__(self, manga_id, api):
        """
        Nothing to see here, move along.
        """
        self.logger = logging.getLogger('mdapi.manga')
        self.api = api
        if isinstance(manga_id, int):
            self.manga_id = self.convert_legacy_id(manga_id)
        else:
            self.manga_id = manga_id
        self.load_data()
        
    def load_data(self):
        self.data = self.api.make_request(request_uri='manga/{}'.format(self.manga_id))["data"]
        self.title = self.data["attributes"]["title"]["en"]
        parser = bbcode.Parser(escape_html=False)
        parser.add_simple_formatter('spoiler', '<span class="spoiler">%(value)s</span>')
        self.description = parser.format(self.data["attributes"]["description"]["en"])
        self.alt_titles = self.data["attributes"]["altTitles"]

    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        new_uuid = requests.post('{}/legacy/mapping'.format(self.api), data=payload).json()[0]["data"]["attributes"]["newId"]
        self.logger.debug("Converted legacy ID {} to new UUID {}".format(manga_id, new_uuid))
        return new_uuid

    def get_chapters(self, limit=10, offset=0, language="en"):
        """
        Returns a list of chapters for this Manga
        """
        # TODO: Come back to this later. Search said 54 results, only 26 actually returned with offsets.
        #response = requests.get('{}/chapter?manga={}&limit={}&offset={}&translatedLanguage={}'.format(self.api, self.manga_id, limit, offset, language))
        response = self.api.make_request(request_uri='chapter?manga={}&limit={}&offset={}'.format(self.manga_id, limit, offset))
        self.total_chapters = response["total"]
        return [ Chapter(self.manga_id, x, self.api) for x in response["results"] ]
