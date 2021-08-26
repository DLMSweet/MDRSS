import json
from json import JSONDecodeError
import os
import base64
from memoization import cached
import requests

class MangadexAPI():
    def __init__(self, api_url):
        self.api_url = api_url

    @cached
    def get_manga(self, manga_id):
        return Manga(manga_id, self.api_url)

    @cached
    def search_manga(self, title, offset=0):
        search_results = requests.get('{}/manga?title={}&offset={}'.format(self.api_url, title, offset))
        if search_results.status_code == 200:
            return search_results.json()
        return None

    @cached
    def get_chapter(self, chapter_id):
        chapter = Chapter(api_url=self.api_url)
        chapter.load_from_uuid(chapter_id)
        return chapter

    def cache_stats(self):
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
    def __init__(self, manga=None, data=None, api_url=None):
        self.api_url = api_url
        self.data = data
        self.manga = manga
        if self.data:
            self.load_data()

    def load_data(self):
        self.chapter_id = self.data["data"]["id"]
        self.chapter = self.data['data']['attributes']['chapter']
        self.volume = self.data['data']['attributes']['volume']
        self.published = self.data['data']['attributes']['publishAt']
        self.created = self.data['data']['attributes']['createdAt']
        self.language = self.data['data']['attributes']['translatedLanguage']
        self.hash = self.data['data']['attributes']['hash']
        self.image_list = self.data['data']['attributes']['data']

    def load_from_uuid(self, chapter_id):
        self.data = requests.get('{}/chapter/{}'.format(self.api_url, chapter_id)).json()
        self.load_data()

    def get_image_server(self):
        try:
            return requests.get('{}/at-home/server/{}'.format(self.api_url, self.chapter_id)).json()["baseUrl"]
        except:
            print("Failed to get image server to use for downloads")
            raise Exception
            
    def get_image_urls(self):
        image_server = self.get_image_server()
        images = []
        for image in self.image_list:
           images.append("{}/data/{}/{}".format(image_server, self.hash, image))
        return images
           
    async def send_report(self, image_url, success=False, downloaded_bytes=0, duration=0, cached=False):
        report = json.dumps({ "url": image_url, "success": success, "bytes": downloaded_bytes, "duration": duration, "cached": cached })
        requests.post("{}/report".format(self.api_url), data=report)

    async def get_image(self, image, report=True):
        image_server = self.get_image_server()
        image_url = "{}/data/{}/{}".format(image_server, self.hash, image)
        try:
            data = requests.get(image_url)
        except requests.exceptions.ConnectionError:
            if report:
                await self.send_report(image_url)
            return None
        if data.status_code == 200:
            if report:
                await self.send_report(image_url, 
                                 success=True, 
                                 downloaded_bytes=len(data.content), 
                                 duration=int(data.elapsed.total_seconds()*1000), 
                                 cached=data.headers['X-Cache'])
            return data
        # By default, send a failing report. This doesn't get hit if we had a success above.
        if report:
            await self.send_report(image_url)
        return None

    async def get_image_bytes(self, image, tries=0):
        if tries > 2:
            return None
        image_data = await self.get_image(image)
        if image_data is None:
            return await self.get_image_bytes(image, tries=tries+1)
        content_type = image_data.headers['content-type']
        encoded_image = base64.b64encode(image_data.content).decode('utf-8')
        return "data:{};base64,{}".format(content_type, encoded_image)

    def download_images(self):
        images_basedir = "{}/{}".format(self.manga, self.chapter_id)
        if not os.path.isdir(images_basedir):
            os.mkdir(images_basedir)
        for image in self.image_list:
            if os.path.isfile('{}/{}'.format(images_basedir, image)):
                print("Skipping {}".format(image))
                continue
            reponse = self.get_image(image)
            if response and response.status_code == 200:
                with open('{}/{}'.format(images_basedir, image), "wb") as output:
                    output.write(data.content)
            
    def __str__(self):
        return "Volume {}, Chapter {} ({})".format(self.volume, self.chapter, self.language)

class Manga():
    def __init__(self, manga_id, api_url):
        self.api_url = api_url
        if isinstance(manga_id, int):
            self.manga_id = self.convert_legacy_id(manga_id)
        else:
            self.manga_id = manga_id

        self.data = requests.get('{}/manga/{}'.format(self.api_url, self.manga_id)).json()["data"]
        self.title = self.data["attributes"]["title"]["en"]

    def convert_legacy_id(self, manga_id):
        payload = json.dumps({ "type": "manga", "ids": [ manga_id ] })
        return requests.post('{}/legacy/mapping'.format(self.api_url), data=payload).json()[0]["data"]["attributes"]["newId"]

    def get_chapters(self, limit=10, offset=0):
        response = requests.get('{}/chapter?manga={}&limit={}&offset={}'.format(self.api_url, self.manga_id, limit, offset)).json()
        return [ Chapter(self.manga_id, x, self.api_url) for x in response["results"] ]

    def get_total_chapters(self):
        response = requests.get('{}/chapter?manga={}'.format(self.api_url, self.manga_id)).json()
        return response["total"]
        

