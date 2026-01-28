import math
from urllib.parse import urlencode
from flask import request

MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20

def _page_params():
    page = request.args.get("page", type=int) or 1
    per_page = request.args.get("per_page", type=int) or DEFAULT_PER_PAGE

    if page < 1:
        page = 1
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE

    return page, per_page

def _link(page, per_page):
    args = dict(request.args)
    args["page"] = page
    args["per_page"] = per_page
    return f"{request.base_url}?{urlencode(args)}"

def paginate(query):
    page, per_page = _page_params()

    total_items = query.order_by(None).count()
    total_pages = max(1, math.ceil(total_items / per_page))
    if page > total_pages:
        page = total_pages

    items = (
        query
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    links = {"self": _link(page, per_page)}
    if page > 1:
        links["prev"] = _link(page - 1, per_page)
    if page < total_pages:
        links["next"] = _link(page + 1, per_page)

    return items, {
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
    }, links
