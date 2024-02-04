# pylint: disable=line-too-long
# pylint: disable=logging-format-interpolation
# pylint: disable=missing-module-docstring
import logging
import re
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

    def handle_tags(self, matched):
        text = matched.group(2)
        if matched.group(1) == "**":
            return f'<strong>{text}</strong>'
        else:
            return f'<em><strong>{text}</strong></em>'

    def handle_urls(self, matched):
        text = matched.group(2)
        url = matched.group(3)
        if matched.group(1):
            # Embed
            return f'<img src="{url}" alt="{text}">'
        else:
            return f'<a href="{url}">{text}</a>'

    def parse_description(self, description: str):
        parser = bbcode.Parser(escape_html=False, replace_links=False)
        parser.add_simple_formatter('spoiler', '<span class="spoiler">%(value)s</span>')
        parser.add_simple_formatter('***', '<em><strong>%(value)s</strong></em>')

        parsed_data = re.sub(r'(!)?\[(.*)\]\(<?(https?://.*)>?\)', self.handle_urls, description, flags=re.IGNORECASE)
        parsed_data = re.sub(r'([\*]{2,3})(.*?)([\*]{2,3})', self.handle_tags, parsed_data)
        self.description = parser.format(parsed_data)

    def load_data(self):
        """
        Loads the data for a Manga UUID from the API
        """
        self.data = self.api.make_request('manga/{}'.format(self.manga_id))
        if self.data is None:
            raise MangaNotFound
        # Try to load the english title first, and failing that try the first available one.
        possible_langs = list(self.data["data"]["attributes"]["title"].keys())
        try:
            self.title = self.data["data"]["attributes"]["title"]["en"]
        except KeyError:
             self.title = self.data["data"]["attributes"]["title"][possible_langs[0]]
        # Check if a description exists first
        possible_langs = None
        if self.data["data"]["attributes"]["description"]:
            possible_langs = list(self.data["data"]["attributes"]["description"].keys())
            # Try to load the english one, because I'm english.
            try:
                self.parse_description(self.data["data"]["attributes"]["description"]["en"])
            except KeyError:
                # Failing that, load the first possible one.
                self.parse_description(self.data["data"]["attributes"]["description"][possible_langs[0]])
        else:
            self.description = 'No Description'
        self.alt_titles = self.data["data"]["attributes"]["altTitles"]

