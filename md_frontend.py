from uuid import UUID
import json
from typing import Union
import requests
import quart.flask_patch
from quart import Quart, flash, render_template, request, Response, make_push_promise, url_for
from flask_pydantic import validate
from flask_paginate import Pagination, get_page_parameter, get_page_args
from flask_bootstrap import Bootstrap
from lib.mdapi import MangadexAPI

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
            await make_push_promise(url_for('static', filename='css/style.css'))
            await make_push_promise(url_for('static', filename='css/bootstrap.min.css'))
            await make_push_promise(url_for('static', filename='js/jquery-3.2.1.slim.min.js'))
            await make_push_promise(url_for('static', filename='js/popper.min.js'))
            await make_push_promise(url_for('static', filename='js/bootstrap.min.js'))
            return await render_template('index.html', results=results, pagination=pagination)
        await flash("No results found", "warning")
    await make_push_promise(url_for('static', filename='css/style.css'))
    await make_push_promise(url_for('static', filename='css/bootstrap.min.css'))
    await make_push_promise(url_for('static', filename='js/jquery-3.2.1.slim.min.js'))
    await make_push_promise(url_for('static', filename='js/popper.min.js'))
    await make_push_promise(url_for('static', filename='js/bootstrap.min.js'))
    return await render_template('index.html')

@app.route('/stats/', methods=["GET"])
@validate()
async def print_stats():
    return MDAPI.cache_stats()

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
            total=manga.total_chapters,
            record_name="chapters",
            format_total=True,
            format_number=True,
            page_parameter="p",
            per_page_parameter="pp",
        )
    else:
        pagination = None
    await make_push_promise(url_for('static', filename='css/style.css'))
    await make_push_promise(url_for('static', filename='css/bootstrap.min.css'))
    await make_push_promise(url_for('static', filename='js/jquery-3.2.1.slim.min.js'))
    await make_push_promise(url_for('static', filename='js/popper.min.js'))
    await make_push_promise(url_for('static', filename='js/bootstrap.min.js'))
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
    chapter = MDAPI.get_chapter(chapter_id)
    await make_push_promise(url_for('static', filename='css/style.css'))
    await make_push_promise(url_for('static', filename='css/bootstrap.min.css'))
    await make_push_promise(url_for('static', filename='js/jquery-3.2.1.slim.min.js'))
    await make_push_promise(url_for('static', filename='js/popper.min.js'))
    await make_push_promise(url_for('static', filename='js/bootstrap.min.js'))
    await make_push_promise(url_for('static', filename='css/reader.css'))
    for image in chapter.image_list:
        await make_push_promise(url_for("get_image", chapter_id=chapter.chapter_id, image_id=image))
    return await render_template('reader.html', chapter=chapter)

@app.route('/reader/<chapter_id>/<image_id>', methods=["GET"])
@validate()
async def get_image(chapter_id: UUID, image_id: str):
    """
    Returns an image from the MD@H network
    Done this way to provide timing and response data to the MD@H network
    """
    chapter = MDAPI.get_chapter(chapter_id)
    image_resp = await chapter.get_image(image_id)
    try:
        response = Response(image_resp.content)
    except AttributeError:
        # Failed to get an image
        return Response("Failed  to get image", 500)
    response.headers['Content-Type'] = image_resp.headers['Content-Type']
    return response

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
