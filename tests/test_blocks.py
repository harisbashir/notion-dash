import pytest
from markupsafe import Markup

from app.blocks import render_blocks, text_to_blocks


def block(kind, text="Example", **values):
    return {
        "object": "block",
        "type": kind,
        kind: {
            "rich_text": [
                {
                    "type": "text",
                    "plain_text": text,
                    "text": {"content": text},
                    "annotations": {},
                }
            ],
            **values,
        },
    }


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("paragraph", "<p>Example</p>"),
        ("heading_1", "<h1>Example</h1>"),
        ("heading_2", "<h2>Example</h2>"),
        ("heading_3", "<h3>Example</h3>"),
        ("bulleted_list_item", "<ul><li>Example</li></ul>"),
        ("numbered_list_item", "<ol><li>Example</li></ol>"),
        ("quote", "<blockquote>Example</blockquote>"),
        ("callout", '<aside class="callout">Example</aside>'),
        ("code", "<pre><code>Example</code></pre>"),
        ("divider", "<hr>"),
    ],
)
def test_block_type(kind, expected):
    rendered = render_blocks([block(kind)])
    assert isinstance(rendered, Markup)
    assert str(rendered) == expected


@pytest.mark.parametrize("checked", [True, False])
def test_to_do(checked):
    result = str(render_blocks([block("to_do", checked=checked)]))
    assert 'type="checkbox"' in result
    assert "disabled" in result
    assert (" checked" in result) == checked
    assert "Example" in result


def test_escapes_html():
    result = str(render_blocks([block("paragraph", '<script>alert("x")</script>')]))
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "&lt;/script&gt;" in result


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("javascript:alert(1)", False),
        ("data:text/html,bad", False),
        ("file:///etc/passwd", False),
        ("//example.com", False),
        ("java\nscript:alert(1)", False),
        ("https://example.com/?x=1&y=2", True),
        ("HTTP://example.com", True),
        ("mailto:example@example.com", True),
    ],
)
def test_link_scheme_allowlist(url, allowed):
    data = block("paragraph", "Click <here>")
    data["paragraph"]["rich_text"][0]["text"]["link"] = {"url": url}
    rendered = str(render_blocks([data]))
    assert ("<a " in rendered) == allowed
    assert "Click &lt;here&gt;" in rendered
    if not allowed:
        assert "href=" not in rendered


def test_link_attribute_escaped():
    data = block("paragraph")
    data["paragraph"]["rich_text"][0]["href"] = 'https://example.com/" onclick="bad'
    result = str(render_blocks([data]))
    assert 'href="https://example.com/&#34; onclick=&#34;bad"' in result


def test_rich_text_annotations():
    data = block("paragraph")
    data["paragraph"]["rich_text"][0]["annotations"] = {
        "bold": True,
        "italic": True,
        "code": True,
        "strikethrough": True,
    }
    result = str(render_blocks([data]))
    for tag in ["strong", "em", "code", "s"]:
        assert f"<{tag}>" in result and f"</{tag}>" in result
    assert "Example" in result


def test_list_grouping():
    result = str(
        render_blocks(
            [
                block("bulleted_list_item", "a"),
                block("bulleted_list_item", "b"),
                block("numbered_list_item", "c"),
                block("numbered_list_item", "d"),
                block("paragraph", "break"),
                block("bulleted_list_item", "e"),
            ]
        )
    )
    assert (
        result == "<ul><li>a</li><li>b</li></ul><ol><li>c</li><li>d</li></ol>"
        "<p>break</p><ul><li>e</li></ul>"
    )


def test_text_to_blocks_splits_long_line():
    result = text_to_blocks("first\n\n" + "x" * 4500 + "\nlast\n   \n")
    assert len(result) == 3
    assert all(b["object"] == "block" and b["type"] == "paragraph" for b in result)
    assert result[0]["paragraph"]["rich_text"][0]["text"]["content"] == "first"
    texts = result[1]["paragraph"]["rich_text"]
    assert [len(t["text"]["content"]) for t in texts] == [2000, 2000, 500]
    assert "".join(t["text"]["content"] for t in texts) == "x" * 4500
    assert result[2]["paragraph"]["rich_text"][0]["text"]["content"] == "last"
    assert text_to_blocks("") == []


def test_unsupported_block():
    assert (
        str(render_blocks([block("image")]))
        == '<div class="unsupported">This part can only be viewed in Notion.</div>'
    )


def test_code_is_literal_and_escaped():
    data = block("code", "<a>\nline")
    data["code"]["rich_text"][0]["annotations"] = {"bold": True}
    data["code"]["rich_text"][0]["href"] = "https://example.com"
    assert str(render_blocks([data])) == "<pre><code>&lt;a&gt;\nline</code></pre>"
