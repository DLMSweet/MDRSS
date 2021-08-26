# pylint: disable=line-too-long
# pylint: disable=logging-format-interpolation
# pylint: disable=missing-module-docstring
import logging
import bbcode

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
        self.manga_id = manga_id
        self.total_chapters = None
        self.load_data()

    def load_data(self):
        """
        Loads the data for a Manga UUID from the API
        """
        self.data = self.api.make_request('manga/{}'.format(self.manga_id))
        if self.data is None:
            raise MangaNotFound
        self.title = self.data["data"]["attributes"]["title"]["en"]
        parser = bbcode.Parser(escape_html=False)
        parser.add_simple_formatter('spoiler', '<span class="spoiler">%(value)s</span>')
        self.description = parser.format(self.data["data"]["attributes"]["description"]["en"])
        self.alt_titles = self.data["data"]["attributes"]["altTitles"]

