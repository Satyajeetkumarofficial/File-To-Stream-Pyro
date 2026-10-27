import os
import logging
import urllib.parse

import jinja2

from web.utils.Template import rexbots_template
from info import *
from web.server import multi_clients, work_loads, StreamBot
from utils import get_size
from web.server.exceptions import InvalidHash
from web.utils.custom_dl import get_byte_streamer, pick_client_index

log = logging.getLogger("web")

_BASE = os.path.join("web", "template")
_templates: dict = {}


def _get_template(name: str) -> jinja2.Template:
    """Compile each HTML template once and keep it in memory."""
    tpl = _templates.get(name)
    if tpl is None:
        with open(os.path.join(_BASE, name), "r", encoding="utf-8") as f:
            tpl = jinja2.Template(f.read())
        _templates[name] = tpl
    return tpl


async def render_page(id, secure_hash: str, src: str = None) -> str:
    id = int(id)

    # Step 1: file properties (cached + de-duplicated, 1 Telegram call at most)
    index = pick_client_index() if multi_clients else 0
    client = multi_clients.get(index, StreamBot)
    file_data = await get_byte_streamer(client).get_file_properties(id)

    # Step 2: validate secure_hash
    if not secure_hash or file_data.unique_id[:6] != secure_hash:
        log.debug("Invalid hash for message %s", id)
        raise InvalidHash

    # Step 3: build file URL
    url_base = URL if URL.endswith("/") else URL + "/"
    src = urllib.parse.urljoin(url_base, f"{id}?hash={secure_hash}")

    # Step 4: type + size (size is already known: no request to our own server)
    mime = file_data.mime_type or "application/octet-stream"
    tag = mime.split("/")[0].strip()
    file_size = get_size(file_data.file_size or 0)
    template_file = "watch.html" if tag in ("video", "audio") else "dl.html"

    # Step 5: render
    try:
        template = _get_template(template_file)
    except Exception as e:
        log.error("Error reading template: %s", e)
        return "Template Error"

    raw_name = file_data.file_name if file_data.file_name and file_data.file_name != "Unnamed" else None
    file_name = raw_name.replace("_", " ") if raw_name else f"File_{id}.mkv"
    tg_link = f"https://t.me/{BOT_USERNAME}?start=file_{id}"

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        file_unique_id=file_data.unique_id,
        template_ne=rexbots_template.NAME,
        disclaimer=rexbots_template.DISCLAIMER,
        report_link=rexbots_template.REPORT_LINK,
        colours=rexbots_template.COLOURS,
        tg_button=tg_link,
    )
