# pylint: disable=line-too-long
# pylint: disable=missing-module-docstring
from uuid import UUID
from typing import Union
import quart.flask_patch # pylint: disable=unused-import
from quart import Quart, flash, render_template, request, Response, make_push_promise, url_for, redirect, abort
from flask_pydantic import validate
from flask_paginate import Pagination, get_page_parameter, get_page_args
from flask_bootstrap import Bootstrap
from lib.mdapi import MangadexAPI, APIError, MangaNotFound, ChapterNotFound
from lib.mdrss import RSSFeed

app = Quart(__name__)
app.secret_key = 'much secret very secure'
Bootstrap(app)

API_URL = "https://api.mangadex.org"
MDAPI = MangadexAPI(API_URL)
RSS = RSSFeed(API_URL)

@app.errorhandler(404)
async def page_not_found(error):
    """
    Flash them. Let them look upon their error
    """
    await flash("{}: That page doesn't exist".format(error), "warning")
    return redirect(url_for('index'))

@app.errorhandler(400)
async def validation_error(error):
    """
    Flash them. Let them look upon their error
    """
    await flash("{}: Something was wrong with your request".format(error), "warning")
    return redirect(url_for('index'))

@app.route('/', methods=["GET"])
async def index():
    """
    Wow such index
    much front page
    """
    page = request.args.get(get_page_parameter(), type=int, default=1)
    page, per_page, offset = get_page_args(page_parameter="p", per_page_parameter="pp", pp=10) # pylint: disable=unbalanced-tuple-unpacking

    if request.args.get("search"):
        if per_page:
            total_results, results = MDAPI.search_manga(request.args.get("search"), offset=offset)
        if results:
            pagination = get_pagination(
                p=page,
                pp=per_page,
                total=total_results,
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

@app.route('/manga/<manga_id>', methods=["GET"])
@validate()
async def get_manga(manga_id: Union[UUID, int]):
    """
    Returns the page for a Manga, including a list
    of all the chapters
    """
    try:
        manga = MDAPI.get_manga(manga_id)
    except MangaNotFound:
        await flash("Could not find manga with ID of {}".format(manga_id), "warning")
        return redirect(url_for('index'))

    page = request.args.get(get_page_parameter(), type=int, default=1)
    page, per_page, offset = get_page_args(page_parameter="p", per_page_parameter="pp", pp=10) # pylint: disable=unbalanced-tuple-unpacking
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

@app.route('/rss/manga/<manga_id>', methods=["GET"])
@validate()
async def get_manga_rss(manga_id: Union[UUID, int]):
    """
    RSS feed generator
    """
    if request.args.get("lang"):
        language_filter = request.args.getlist("lang")
        feed_data = RSS.generate_feed(manga_id, language_filter=language_filter)
    else:
        feed_data = RSS.generate_feed(manga_id)
    if feed_data is None:
        abort(404)
    return Response(feed_data, mimetype='text/xml')


@app.route('/atom/manga/<manga_id>', methods=["GET"])
@validate()
async def get_manga_atom(manga_id: Union[UUID, int]):
    """
    Atom feed generator
    """
    if request.args.get("lang"):
        language_filter = request.args.getlist("lang")
        feed_data = RSS.generate_feed(manga_id, language_filter=language_filter, type="atom")
    else:
        feed_data = RSS.generate_feed(manga_id, type="atom")
    if feed_data is None:
        abort(404)
    return Response(feed_data, mimetype='text/xml')

@app.route('/reader/<chapter_id>', methods=["GET"])
@validate()
async def read_chapter(chapter_id: UUID):
    """
    Returns the reader page for a chapter,
    loading images directly from the MD@H network
    """
    try:
        chapter = MDAPI.get_chapter(chapter_id)
    except ChapterNotFound:
        abort(404)
    await make_push_promise(url_for('static', filename='css/style.css'))
    await make_push_promise(url_for('static', filename='css/bootstrap.min.css'))
    await make_push_promise(url_for('static', filename='js/jquery-3.2.1.slim.min.js'))
    await make_push_promise(url_for('static', filename='js/popper.min.js'))
    await make_push_promise(url_for('static', filename='js/bootstrap.min.js'))
    await make_push_promise(url_for('static', filename='css/reader.css'))
    for image in chapter.image_list:
        await make_push_promise(url_for("get_image", chapter_id=chapter.chapter_id, image_id=image))
    return await render_template('reader.html', chapter=chapter)

@app.route('/image/<chapter_id>/<image_id>', methods=["GET"])
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
