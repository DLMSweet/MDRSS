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
        # Try to load the english title first, and failing that try the first available one.
        possible_langs = self.data["data"]["attributes"]["title"].keys()
        try:
            self.title = self.data["data"]["attributes"]["title"]["en"]
        except KeyError:
             self.title = self.data["data"]["attributes"]["title"][possible_langs[0]]
        parser = bbcode.Parser(escape_html=False)
        parser.add_simple_formatter('spoiler', '<span class="spoiler">%(value)s</span>')
        # Check if a description exists first
        possible_langs = None
        if self.data["data"]["attributes"]["description"]:
            possible_langs = self.data["data"]["attributes"]["description"].keys()
            # Try to load the english one, because I'm english.
            try:
                self.description = parser.format(self.data["data"]["attributes"]["description"]["en"])
            except KeyError:
                # Failing that, load the first possible one.
                self.description = parser.format(self.data["data"]["attributes"]["description"][possible_langs[0]])
        else:
            self.description = 'No Description'
        self.alt_titles = self.data["data"]["attributes"]["altTitles"]

