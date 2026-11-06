"""v0.9.4 UI regression checks; uses only the Python standard library."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
EXPERIENCE = (ROOT / 'static' / 'experience.js').read_text(encoding='utf-8')
CSS = (ROOT / 'static' / 'experience.css').read_text(encoding='utf-8')


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


parser = Elements()
parser.feed(HTML)
ELEMENTS = parser.items


def attr_of(item_id):
    matches = [attrs for _, attrs in ELEMENTS if attrs.get('id') == item_id]
    assert len(matches) == 1, f'Expected one element with ID {item_id}'
    return matches[0]


def test_sidebar_engine_version_and_developer_link_are_hidden():
    assert '<div class="status-dot">' not in HTML
    assert 'class="api-link"' not in HTML
    assert 'Local engine · v0.8' not in APP


def test_assistant_is_circle_and_sixth_guide_step_exists():
    assert attr_of('assistant-toggle')['aria-label'] == 'Ask DataMendry AI assistant'
    assert "$('assistant-toggle')" in EXPERIENCE
    assert '.assistant-toggle { width:58px;height:58px;' in CSS
    guide = HTML.split('<section id="page-guide"', 1)[1].split('</section>', 1)[0]
    assert guide.count('<article') == 6
    attr_of('guide-assistant')
    assert "$('guide-assistant').addEventListener('click'" in EXPERIENCE


def test_open_source_points_to_the_real_repository():
    anchors = [a for tag, a in ELEMENTS if tag == 'a' and 'external' in a.get('class', '').split()]
    assert len(anchors) == 1
    assert anchors[0]['href'] == 'https://github.com/harshsinghps57-spec/datamendry'
    assert {'noopener', 'noreferrer'} <= set(anchors[0]['rel'].split())


def test_only_top_right_account_menu_and_actions_remain():
    for suffix in ('toggle', 'popover', 'label', 'login', 'logout', 'password', 'my-datasets'):
        attr_of(f'profile-{suffix}')
    attr_of('profile-top-name')
    assert 'sidebar-profile profile-widget' not in HTML
    assert 'profile-sidebar-' not in HTML
    assert 'profile-sidebar-' not in EXPERIENCE
    assert 'for (const menu of profileMenus)' in EXPERIENCE
    assert 'await account().logout()' in EXPERIENCE
    assert 'await account().setPassword(pass)' in EXPERIENCE


def test_breadcrumb_navigation_is_clickable():
    attr_of('crumb-workspace')
    assert attr_of('crumb-page')['aria-controls'] == 'crumb-menu'
    assert sum(1 for _, attrs in ELEMENTS if 'data-crumb-page' in attrs) == 6
    assert 'ui()?.navigate(button.dataset.crumbPage)' in EXPERIENCE
    assert 'crumb-page' in APP


def test_footer_replaced_but_storage_limit_still_disclosed():
    assert 'DataMendry account-storage preview' not in APP
    assert 'DataMendry account-storage preview' not in HTML
    assert 'class="storage-disclosure"' in HTML
    assert 'storage quotas' in HTML
    assert 'Avoid uploading sensitive datasets' in HTML


def test_depth_accessibility_and_core_controls_preserved():
    assert '@keyframes dm-v094-scene' in CSS
    assert '@media(prefers-reduced-motion:reduce)' in CSS
    for item in ['file-input', 'demo-button', 'filter-preview', 'filter-download', 'account-panel',
                 'profile-toggle', 'auth-google', 'auth-login']:
        attr_of(item)
    assert '/api/datasets' in APP and '/api/datasets' in EXPERIENCE
