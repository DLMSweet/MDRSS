from uuid import UUID
import json
from typing import Union
import requests
import quart.flask_patch
from quart import Quart, flash, render_template, request
from flask_pydantic import validate
from flask_paginate import Pagination, get_page_parameter, get_page_args
from flask_bootstrap import Bootstrap
from lib.mdapi import MangadexAPI, Chapter

app = Quart(__name__)
app.secret_key = 'much secret very secure'
Bootstrap(app)

API_URL = "https://api.mangadex.org"
MDAPI = MangadexAPI(API_URL)

async def convert_legacy_id(lookup_id, lookup_type="manga"):
    """
    Converts a legacy ID to a new style UUID
    """
    payload = json.dumps({ "type": lookup_type, "ids": [ lookup_id ] })
    return await requests.post('{}/legacy/mapping'.format(API_URL), data=payload).json()[0]["data"]["attributes"]["newId"]


@app.route('/', methods=["GET"])
async def index():
    """
    Wow such index
    much front page
    """
    page = request.args.get(get_page_parameter(), type=int, default=1)
    page, per_page, offset = get_page_args(page_parameter="p", per_page_parameter="pp", pp=10)

    if request.args.get("search"):
        if per_page:
            results = MDAPI.search_manga(request.args.get("search"), offset=offset)
        if results:
            pagination = get_pagination(
                p=page,
                pp=per_page,
                total=results["total"],
                record_name="Manga",
                format_total=True,
                format_number=True,
                page_parameter="p",
                per_page_parameter="pp",
            )
            return await render_template('index.html', results=results, pagination=pagination)
        await flash("No results found", "warning")
    return await render_template('index.html')

@app.route('/manga/<manga_id>', methods=["GET"])
@validate()
async def get_manga(manga_id: Union[UUID, int]):
    """
    Returns the page for a Manga, including a list
    of all the chapters
    """
    if isinstance(manga_id, int):
        manga_id = convert_legacy_id(manga_id)
    manga = MDAPI.get_manga(manga_id)

    page = request.args.get(get_page_parameter(), type=int, default=1)
    page, per_page, offset = get_page_args(page_parameter="p", per_page_parameter="pp", pp=10)
    if per_page:
        chapters = manga.get_chapters(offset=offset)
    if chapters:
        pagination = get_pagination(
            p=page,
            pp=per_page,
            total=manga.get_total_chapters(),
            record_name="chapters",
            format_total=True,
            format_number=True,
            page_parameter="p",
            per_page_parameter="pp",
        )

    return await render_template('manga.html', manga=manga, chapters=chapters, pagination=pagination)

@app.route('/manga/<manga_id>/rss', methods=["GET"])
@validate()
async def get_manga_rss(manga_id: Union[UUID, int]):
    """
    Currently unfinished, at some point will be a RSS feed generator
    """
    if isinstance(manga_id, int):
        manga_id = convert_legacy_id(manga_id)
    manga = MDAPI.get_manga(manga_id)
    chapters = manga.get_chapters()
    return await render_template('feed.rss', manga=manga, chapters=chapters)


@app.route('/reader/<chapter_id>', methods=["GET"])
@validate()
async def read_chapter(chapter_id: UUID):
    """
    Returns the reader page for a chapter,
    loading images directly from the MD@H network
    """
    chapter = Chapter(api_url=API_URL)
    chapter.load_from_uuid(chapter_id)
    images = chapter.get_image_urls()
    return await render_template('reader.html', images=images)


def get_pagination(**kwargs):
    """Returns pagination settings"""
    kwargs.setdefault("record_name", "records")
    return Pagination(
        css_framework="bootstrap4",
        link_size="sm",
        alignment="",
        show_single_page=False,
        **kwargs
    )
