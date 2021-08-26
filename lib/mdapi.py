# pylint: disable=line-too-long
import json
import base64
from memoization import cached
import requests

class MangadexAPI():
    """
    A basic class to handle the Mangadex API
    """
    def __init__(self, api_url):
        """
        Does very little. Just holds the API url
        """
        self.api_url = api_url

    @cached
    def get_manga(self, manga_id):
        """
        Returns a Manga based on it's UUID
        """
        return Manga(manga_id, self.api_url)

    @cached
    def search_manga(self, title, offset=0):
        """
        Returns search results or None if nothing is found
        """
        search_results = requests.get('{}/manga?title={}&offset={}'.format(self.api_url, title, offset))
        if search_results.status_code == 200:
            return search_results.json()
        return None

    @cached
    def get_chapter(self, chapter_id):
        """
        Returns a chapter based on it's ID
        """
        chapter = Chapter(api_url=self.api_url)
        chapter.load_from_uuid(chapter_id)
        return chapter

    def cache_stats(self):
        """
        Prints some stats out about how the cache is doing
        """
        # pylint: disable=no-member
        return json.dumps({"get_manga": { "hits": self.get_manga.cache_info().hits,
                                          "misses": self.get_manga.cache_info().misses,
                                          "size": self.get_manga.cache_info().current_size },
                           "search_manga": { "hits": self.search_manga.cache_info().hits,
                                             "misses": self.search_manga.cache_info().misses,
                                             "size": self.search_manga.cache_info().current_size },
                           "get_chapter": { "hits": self.get_chapter.cache_info().hits,
                                            "misses": self.get_chapter.cache_info().misses,
                                            "size": self.get_chapter.cache_info().current_size }
                            })
class Chapter():
    """
    A Chapter object used to get information about a chapter and
    to pull images for the chapter, including getting a MD@H node
    """
    def __init__(self, manga=None, data=None, api_url=None):
        """
        Just inits the object, nothing to see here. move along
        """
        self.api_url = api_url
        self.data = data
        self.manga = manga
        if self.data:
            self.load_data()

    def load_data(self):
        """
        Copy the data out into attributes to make it easier to
        read without dealing with the JSON object
        """
        self.chapter_id = self.data["data"]["id"]
        self.chapter = self.data['data']['attributes']['chapter']
        self.volume = self.data['data']['attributes']['volume']
        self.published = self.data['data']['attributes']['publishAt']
        self.created = self.data['data']['attributes']['createdAt']
        self.language = self.data['data']['attributes']['translatedLanguage']
        self.hash = self.data['data']['attributes']['hash']
        self.image_list = self.data['data']['attributes']['data']
        self.image_server = self.get_image_server()

    def load_from_uuid(self, chapter_id):
        """
        Get the chapter information from the API based on the UUID
        """
        self.data = requests.get('{}/chapter/{}'.format(self.api_url, chapter_id)).json()
        self.load_data()

    def get_image_server(self):
        """
        Attempt to get a MD@H node to pull images from
        """
        try:
            return requests.get('{}/at-home/server/{}'.format(self.api_url, self.chapter_id)).json()["baseUrl"]
        except:
            print("Failed to get image server to use for downloads")
            raise Exception

    def get_image_urls(self):
        """
        Get the URLs for the images, in case we want to stick them
        directly into a <img> or pass them to something else
        """
        images = []
        for image in self.image_list:
            images.append("{}/data/{}/{}".format(self.image_server, self.hash, image))
        return images

    async def send_report(self, image_url, success=False, downloaded_bytes=0, duration=0, is_cached=False):
        """
        Sends a report about download speed/success/etc to the backend
        """
        report = json.dumps({ "url": image_url, "success": success, "bytes": downloaded_bytes, "duration": duration, "cached": is_cached })
        resp = requests.post("https://api.mangadex.network/report", data=report)
        if not resp.ok:
            print("Failed to report status of image: {} - {}".format(resp.status_code, resp.reason))
            print(resp.json())
            print(report)

    async def get_image(self, image, report=True, tries=0):
        """
        Returns an image in a requests Response object
        """
        if tries > 0:
            # Get a new image server
            self.image_server = self.get_image_server()
        if tries > 3:
            # Guess we'll die
            return None
        image_url = "{}/data/{}/{}".format(self.image_server, self.hash, image)
        try:
            data = requests.get(image_url)
        except requests.exceptions.ConnectionError:
            if report:
                await self.send_report(image_url)
            return await self.get_image(image, report=report, tries=tries+1)
        if data.status_code == 200:
            if report:
                if data.headers['X-Cache'] == "HIT":
                    is_cached = True
                await self.send_report(image_url,
                                 success=True,
                                 downloaded_bytes=len(data.content),
                                 duration=int(data.elapsed.total_seconds()*1000),
                                 is_cached=is_cached)
            return data
        # By default, send a failing report. This doesn't get hit if we had a success above.
        if report:
            await self.send_report(image_url)
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
    def __init__(self, manga_id, api_url):
        """
        Nothing to see here, move along.
        """
        self.api_url = api_url
        if isinstance(manga_id, int):
            self.manga_id = self.convert_legacy_id(manga_id)
        else:
            self.manga_id = manga_id

        self.data = requests.get('{}/manga/{}'.format(self.api_url, self.manga_id)).json()["data"]
        self.title = self.data["attributes"]["title"]["en"]

    def convert_legacy_id(self, manga_id):
        """
        If we were given a legacy ID, figure out what the new UUID is
        """
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        return requests.post('{}/legacy/mapping'.format(self.api_url), data=payload).json()[0]["data"]["attributes"]["newId"]

    def get_chapters(self, limit=10, offset=0):
        """
        Returns a list of chapters for this Manga
        """
        response = requests.get('{}/chapter?manga={}&limit={}&offset={}'.format(self.api_url, self.manga_id, limit, offset)).json()
        return [ Chapter(self.manga_id, x, self.api_url) for x in response["results"] ]

    def get_total_chapters(self):
        """
        Kind of a dirty hack, but just gets the total number of chapters for use in Pagination
        """
        response = requests.get('{}/chapter?manga={}'.format(self.api_url, self.manga_id)).json()
        return response["total"]
