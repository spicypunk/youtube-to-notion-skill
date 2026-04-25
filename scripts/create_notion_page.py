#!/usr/bin/env python3
"""
Create a Notion page from a markdown file.
Converts common markdown to Notion blocks.

Reads NOTION_TOKEN and NOTION_PARENT_PAGE_ID from environment if --token/--parent-id
are not given. Pass the token via env var to keep it out of `ps` output.

Usage:
  create_notion_page.py --title "Title" --markdown /path/to/notes.md
  create_notion_page.py --token secret_xxx --parent-id PAGE_ID --title "Title" --markdown /path/to/notes.md
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def notion_request(method: str, path: str, token: str, body: dict = None) -> dict:
    """Make a Notion API request."""
    url = f"{NOTION_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"Notion API error {e.code}: {body_text}", file=sys.stderr)
        raise


def rich_text(content: str) -> list:
    """Create a Notion rich_text array, handling bold (**text**) and inline code (`code`)."""
    if not content:
        return [{"type": "text", "text": {"content": ""}}]

    parts = []
    # Split on bold and inline code markers
    tokens = re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', content)
    for token in tokens:
        if token.startswith("**") and token.endswith("**"):
            parts.append({
                "type": "text",
                "text": {"content": token[2:-2]},
                "annotations": {"bold": True},
            })
        elif token.startswith("`") and token.endswith("`"):
            parts.append({
                "type": "text",
                "text": {"content": token[1:-1]},
                "annotations": {"code": True},
            })
        elif token:
            parts.append({"type": "text", "text": {"content": token}})
    return parts if parts else [{"type": "text", "text": {"content": content}}]


def markdown_to_blocks(md: str) -> list:
    """Convert markdown to Notion block objects."""
    blocks = []
    lines = md.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip() or "plain text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                    "language": lang if lang in NOTION_LANGUAGES else "plain text",
                },
            })

        # Heading 4+ → Notion only supports H1-H3, so map #### (and deeper) to H3
        elif line.startswith("#### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": rich_text(line.lstrip("#").strip())},
            })

        # Heading 1
        elif line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": rich_text(line[2:].strip())},
            })

        # Heading 2
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": rich_text(line[3:].strip())},
            })

        # Heading 3
        elif line.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": rich_text(line[4:].strip())},
            })

        # Bullet list
        elif re.match(r'^[-*] ', line):
            text = re.sub(r'^[-*] ', '', line)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich_text(text)},
            })

        # Numbered list
        elif re.match(r'^\d+\. ', line):
            text = re.sub(r'^\d+\. ', '', line)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": rich_text(text)},
            })

        # Blockquote
        elif line.startswith("> "):
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": rich_text(line[2:].strip())},
            })

        # Horizontal rule → divider
        elif re.match(r'^-{3,}$', line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # Empty line → skip (Notion handles spacing)
        elif line.strip() == "":
            pass

        # Paragraph
        else:
            # Merge continuation lines into paragraph
            para_lines = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith("#") and not lines[i + 1].startswith("```") and not re.match(r'^[-*\d]', lines[i + 1]):
                i += 1
                para_lines.append(lines[i])
            text = " ".join(para_lines)
            # Truncate to Notion's 2000 char limit per block
            if len(text) > 2000:
                chunks = [text[j:j+2000] for j in range(0, len(text), 2000)]
                for chunk in chunks:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": rich_text(chunk)},
                    })
                i += 1
                continue

            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text(text)},
            })

        i += 1

    return blocks


# Languages Notion supports in code blocks
NOTION_LANGUAGES = {
    "abap", "arduino", "bash", "basic", "c", "clojure", "coffeescript", "c++",
    "c#", "css", "dart", "diff", "docker", "elixir", "elm", "erlang", "flow",
    "fortran", "f#", "gherkin", "glsl", "go", "graphql", "groovy", "haskell",
    "html", "java", "javascript", "json", "julia", "kotlin", "latex", "less",
    "lisp", "livescript", "lua", "makefile", "markdown", "markup", "matlab",
    "mermaid", "nix", "objective-c", "ocaml", "pascal", "perl", "php",
    "plain text", "powershell", "prolog", "protobuf", "python", "r",
    "reason", "ruby", "rust", "sass", "scala", "scheme", "scss", "shell",
    "sql", "swift", "typescript", "vb.net", "verilog", "vhdl", "visual basic",
    "webassembly", "xml", "yaml", "java/c/c++/c#",
}


def create_page(token: str, parent_id: str, title: str, blocks: list) -> str:
    """Create a Notion page and return its URL."""
    # Notion API accepts max 100 blocks per request — chunk if needed
    first_batch = blocks[:100]
    rest = blocks[100:]

    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": first_batch,
    }

    page = notion_request("POST", "/pages", token, payload)
    page_id = page["id"]
    page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    # Append remaining blocks in chunks of 100
    for chunk_start in range(0, len(rest), 100):
        chunk = rest[chunk_start:chunk_start + 100]
        notion_request("PATCH", f"/blocks/{page_id}/children", token, {"children": chunk})

    return page_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=os.environ.get("NOTION_TOKEN"))
    parser.add_argument("--parent-id", default=os.environ.get("NOTION_PARENT_PAGE_ID"))
    parser.add_argument("--title", required=True)
    parser.add_argument("--markdown", required=True)
    args = parser.parse_args()

    if not args.token:
        print("ERROR: Notion token missing. Set NOTION_TOKEN env var (or copy config.env.example to config.env and fill it in) or pass --token.", file=sys.stderr)
        sys.exit(2)
    if not args.parent_id:
        print("ERROR: Notion parent page ID missing. Set NOTION_PARENT_PAGE_ID env var (or copy config.env.example to config.env and fill it in) or pass --parent-id.", file=sys.stderr)
        sys.exit(2)

    with open(args.markdown, "r", encoding="utf-8") as f:
        md = f.read()

    # Strip the leading H1 if it matches the title (avoid duplication)
    first_line = md.splitlines()[0] if md.strip() else ""
    if first_line.startswith("# "):
        md = "\n".join(md.splitlines()[1:]).lstrip()

    blocks = markdown_to_blocks(md)
    print(f"Converting {len(blocks)} blocks to Notion...", file=sys.stderr)

    parent_id = args.parent_id.replace("-", "")
    url = create_page(args.token, parent_id, args.title, blocks)

    print(f"\n✅ Notion page created: {url}")


if __name__ == "__main__":
    main()
