"""Small allowlist for announcement formatting; no dependency on client HTML trust."""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.utils.html import linebreaks
from django.utils.safestring import mark_safe

ALLOWED = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'h2', 'h3', 'blockquote', 'a'}
VOID = {'br'}


def safe_href(value):
    value = (value or '').strip()
    if not value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value) or '\\' in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() in ('https', 'http', 'mailto'):
        return value
    # Relative paths within Encore. Never allow protocol-relative URLs.
    if value.startswith('/') and not value.startswith('//'):
        return value
    return None


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            return
        if tag == 'a':
            href = safe_href(dict(attrs).get('href'))
            if href:
                self.parts.append('<a href="%s" rel="noopener noreferrer">' % escape(href, quote=True))
                self.stack.append('a')
            else:
                self.stack.append(None)
        else:
            self.parts.append('<%s>' % tag)
            if tag not in VOID:
                self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in ALLOWED or tag in VOID or tag not in self.stack:
            return
        # Close tags up to match so malformed markup cannot leak into page.
        while self.stack:
            top = self.stack.pop()
            if top:
                self.parts.append('</%s>' % top)
            if top == tag:
                break

    def handle_data(self, data):
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append('&amp;%s;' % name)

    def handle_charref(self, name):
        self.parts.append('&amp;#%s;' % name)

    def finish(self):
        while self.stack:
            top = self.stack.pop()
            if top:
                self.parts.append('</%s>' % top)
        return ''.join(self.parts)


def sanitize_announcement_html(value):
    cleaner = _Cleaner()
    cleaner.feed(value or '')
    cleaner.close()
    return cleaner.finish()


def display_announcement(value):
    value = value or ''
    if value.lstrip().startswith(('<p>', '<div>', '<h2>', '<h3>', '<ul>', '<ol>', '<blockquote>', '<strong>', '<b>', '<em>', '<i>', '<a ')):
        return mark_safe(sanitize_announcement_html(value))
    return linebreaks(value)
