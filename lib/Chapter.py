# pylint: disable=line-too-long
# pylint: disable=logging-format-interpolation
# pylint: disable=missing-module-docstring
import logging

class Chapter():
    """
    A Chapter object used to get information about a chapter
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
        self.chapter_id = self.data["data"]["id"]
        self.chapter = self.data['data']['attributes']['chapter']
        self.volume = self.data['data']['attributes']['volume']
        self.published = self.data['data']['attributes']['publishAt']
        self.created = self.data['data']['attributes']['createdAt']
        self.language = self.data['data']['attributes']['translatedLanguage']
        self.hash = self.data['data']['attributes']['hash']
        self.manga = [x['id'] for x in self.data['relationships'] if x['type'] == 'manga'][0]


    def load_from_uuid(self, chapter_id):
        """
        Get the chapter information from the API based on the UUID
        """
        response = self.api.make_request('chapter/{}'.format(chapter_id))
        if response is None:
            raise ChapterNotFound
        self.data = response
        self.load_data()

    def __str__(self):
        """
        Returns some basic information about the chapter
        """
        return "Volume {}, Chapter {} ({})".format(self.volume, self.chapter, self.language)

