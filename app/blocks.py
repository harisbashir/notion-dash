from urllib.parse import urlsplit

from markupsafe import Markup, escape

from app.schema import rich_text


def _text(parts, *, literal=False):
    output = []
    for part in parts or []:
        text = part.get("plain_text", (part.get("text") or {}).get("content", ""))
        rendered = str(escape(text))
        if not literal:
            annotations = part.get("annotations") or {}
            for key, tag in [
                ("code", "code"),
                ("bold", "strong"),
                ("italic", "em"),
                ("strikethrough", "s"),
            ]:
                if annotations.get(key):
                    rendered = f"<{tag}>{rendered}</{tag}>"
            link = (part.get("text") or {}).get("link") or {}
            url = part.get("href") or link.get("url")
            if url:
                try:
                    allowed = urlsplit(url).scheme.lower() in {
                        "http",
                        "https",
                        "mailto",
                    }
                except ValueError:
                    allowed = False
                if allowed:
                    rendered = f'<a href="{escape(url)}">{rendered}</a>'
        output.append(rendered)
    return "".join(output)


def render_blocks(blocks: list[dict]) -> Markup:
    output = []
    current_list = None
    tags = {
        "paragraph": "p",
        "heading_1": "h1",
        "heading_2": "h2",
        "heading_3": "h3",
        "quote": "blockquote",
    }
    lists = {"bulleted_list_item": "ul", "numbered_list_item": "ol"}
    for block in blocks:
        kind = block.get("type")
        listing = lists.get(kind)
        if listing != current_list:
            if current_list:
                output.append(f"</{current_list}>")
            if listing:
                output.append(f"<{listing}>")
            current_list = listing
        value = block.get(kind) or {}
        text = _text(value.get("rich_text"), literal=kind == "code")
        if listing:
            output.append(f"<li>{text}</li>")
        elif kind in tags:
            tag = tags[kind]
            output.append(f"<{tag}>{text}</{tag}>")
        elif kind == "to_do":
            checked = " checked" if value.get("checked") else ""
            output.append(
                f'<div class="to-do"><input type="checkbox" disabled{checked}> '
                f"{text}</div>"
            )
        elif kind == "callout":
            output.append(f'<aside class="callout">{text}</aside>')
        elif kind == "code":
            output.append(f"<pre><code>{text}</code></pre>")
        elif kind == "divider":
            output.append("<hr>")
        else:
            output.append(
                '<div class="unsupported">This part can only be viewed in Notion.</div>'
            )
    if current_list:
        output.append(f"</{current_list}>")
    return Markup("".join(output))


def text_to_blocks(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": rich_text(line)},
        }
        for line in text.splitlines()
        if line.strip()
    ]
