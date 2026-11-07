#!/usr/bin/env python3
"""Build the Belfry vs AWX comparison page.

Component versions are read from the source files of the last AWX release and
of Belfry's main branches, and support status comes from endoflife.date. The
curated list of changes comes from changes.yml. The page is written to
_site/index.html.
"""

import datetime
import html
import json
import os
import re
import urllib.error
import urllib.request

import yaml

# Last AWX releases (July 2024). awx-ee has no release tags; the 24.6.1 image
# was built from its main branch, so the last commit before the release is used.
UPSTREAM = {
    'app': ('ansible/awx', '24.6.1'),
    'ee': ('ansible/awx-ee', '00fe06c671'),
    'operator': ('ansible/awx-operator', '2.19.1'),
}
# Last ansible/awx commit merged into belfry (created from a498310675, synced
# since); update after an upstream sync, see SYNCING.md in belfry-project/.github.
BELFRY_UPSTREAM_BASE = 'fe6cd9d45a'
# Belfry repositories, with the last upstream commit merged into each (None for new repositories)
BELFRY_REPOS = {
    'belfry': BELFRY_UPSTREAM_BASE,
    'belfry-ee': 'b8da008',
    'belfry-operator': '76470a4',
    'helm-charts': 'fc0b6db',
    'belfry-ui': '96dcf0b',
    '.github': None,
    'belfry-project.github.io': None,
}

# Python version of the base image, used when the execution environment does not set one
SYSTEM_PYTHON = {'9': '3.9', '10': '3.12'}
# Base images, matched as "<image>:<tag>", with the name of the distribution and its endoflife.date product
BASE_IMAGES = [
    (r'quay\.io/centos/centos:stream(\d+)', 'CentOS Stream', 'centos-stream'),
    (r'quay\.io/almalinuxorg/almalinux:(\d+)', 'AlmaLinux', 'almalinux'),
]

TODAY = datetime.datetime.now(datetime.UTC).date()


def fetch(url, accept=None):
    headers = {'User-Agent': 'belfry-comparison-page'}
    if accept:
        headers['Accept'] = accept
    if 'api.github.com' in url and os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f'Bearer {os.environ["GITHUB_TOKEN"]}'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return response.read().decode()


def latest_release():
    """Tag of the latest final Belfry release, or 'main' if there is none yet."""
    try:
        return json.loads(fetch('https://api.github.com/repos/belfry-project/belfry/releases/latest'))['tag_name']
    except urllib.error.HTTPError as e:
        if e.code == 404:  # no release yet
            return 'main'
        raise


# belfry, belfry-ee and belfry-operator are released together with the same tag
BELFRY_REF = os.environ.get('BELFRY_REF') or latest_release()
BELFRY_LABEL = 'Belfry (main)' if BELFRY_REF == 'main' else f'Belfry {BELFRY_REF}'
BELFRY = {
    'app': ('belfry-project/belfry', BELFRY_REF),
    'ee': ('belfry-project/belfry-ee', BELFRY_REF),
    'operator': ('belfry-project/belfry-operator', BELFRY_REF),
}


def source(component, ref_map, path):
    repo, ref = ref_map[component]
    return fetch(f'https://raw.githubusercontent.com/{repo}/{ref}/{path}')


def search(pattern, text, what):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f'Could not find {what} (pattern {pattern!r})')
    return match.group(1)


# Extractors: each returns the version string for one side (upstream or Belfry)


def base_os(text, prefix=''):
    """Return (distribution and major version, e.g. 'AlmaLinux 10', major version) of the first base image after prefix."""
    for pattern, name, _product in BASE_IMAGES:
        match = re.search(prefix + pattern, text, re.MULTILINE)
        if match:
            return f'{name} {match.group(1)}', match.group(1)
    raise ValueError(f'Could not find the base image (prefix {prefix!r})')


def os_product(version):
    """endoflife.date product for a base_os() name."""
    return next(product for _pattern, name, product in BASE_IMAGES if version.startswith(name + ' '))


def app_base_os(refs):
    return base_os(source('app', refs, 'tools/ansible/roles/dockerfile/templates/Dockerfile.j2'), '^FROM ')[0]


def app_python(refs):
    return search(r'\bpython(3\.\d+)\b', source('app', refs, 'tools/ansible/roles/dockerfile/templates/Dockerfile.j2'), 'Python version')


def app_node(refs):
    dockerfile = source('app', refs, 'tools/ansible/roles/dockerfile/templates/Dockerfile.j2')
    if 'nodejs:{{ nodejs_version }}' in dockerfile or 'nodejs{{ nodejs_version }}' in dockerfile:
        return source('app', refs, '.nvmrc').strip()
    match = re.search(r'\bn (\d+)\.\d+\.\d+', dockerfile) or re.search(r'nodejs:(\d+)', dockerfile)
    if not match:
        raise ValueError('Could not find the Node.js version')
    return match.group(1)


def app_django(refs):
    return search(r'^django==([\d.]+)', source('app', refs, 'requirements/requirements.txt'), 'Django version')


def app_receptor(refs):
    tag = search(r'^RECEPTOR_IMAGE \?= \S+?:([^\s@]+)', source('app', refs, 'Makefile'), 'receptor image')
    return tag + (' (moving tag)' if not re.match(r'v?\d', tag) else '')


def ee_base_os(refs):
    return base_os(source('ee', refs, 'execution-environment.yml'), 'name: ')[0]


def ee_python(refs):
    spec = source('ee', refs, 'execution-environment.yml')
    match = re.search(r'python_path: /usr/bin/python(3\.\d+)', spec)
    if match:
        return match.group(1)
    return f'{SYSTEM_PYTHON[base_os(spec, "name: ")[1]]} (system default)'


def ee_ansible_core(refs):
    requirement = search(r'package_pip: ansible-core(\S*)', source('ee', refs, 'execution-environment.yml'), 'ansible-core requirement')
    minimum = re.search(r'>=(\d+)\.(\d+)', requirement)
    if minimum:
        return f'{minimum.group(1)}.{minimum.group(2)}'
    below = re.search(r'<(\d+)\.(\d+)', requirement)
    if below:
        return f'{below.group(1)}.{int(below.group(2)) - 1}'
    raise ValueError(f'Cannot interpret ansible-core requirement {requirement!r}')


def operator_base(refs):
    return search(
        r'^FROM (?:quay\.io/operator-framework|ghcr\.io/belfry-project)/ansible-operator:(v[\d.]+)',
        source('operator', refs, 'Dockerfile'),
        'ansible-operator base image',
    )


def operator_kubernetes_core(refs):
    requirements = yaml.safe_load(source('operator', refs, 'requirements.yml'))
    for collection in requirements['collections']:
        if collection['name'] == 'kubernetes.core':
            return str(collection['version'])
    raise ValueError('kubernetes.core not found in requirements.yml')


def operator_redis(refs):
    return search(r'^_redis_image_version: "?([\w.]+)"?', source('operator', refs, 'roles/installer/defaults/main.yml'), 'Redis version')


def operator_init_os(refs):
    return base_os(source('operator', refs, 'roles/installer/defaults/main.yml'), '^_init_projects_container_image: ')[0]


def operator_postgres(refs):
    return search(r'^_postgres_image: \S*postgresql-(\d+)-', source('operator', refs, 'roles/installer/defaults/main.yml'), 'PostgreSQL version')


# Rows of the comparison table: (group, component, extractor, endoflife.date product)
ROWS = [
    ('Belfry / AWX application', 'Base operating system', app_base_os, 'os'),
    ('Belfry / AWX application', 'Python', app_python, 'python'),
    ('Belfry / AWX application', 'Node.js (UI build)', app_node, 'nodejs'),
    ('Belfry / AWX application', 'Django', app_django, 'django'),
    ('Belfry / AWX application', 'Receptor', app_receptor, None),
    ('Execution environment', 'Base operating system', ee_base_os, 'os'),
    ('Execution environment', 'Python', ee_python, 'python'),
    ('Execution environment', 'ansible-core', ee_ansible_core, 'ansible-core'),
    ('Kubernetes operator', 'ansible-operator base image', operator_base, None),
    ('Kubernetes operator', 'kubernetes.core collection', operator_kubernetes_core, None),
    ('Kubernetes operator', 'Redis (default)', operator_redis, 'redis'),
    ('Kubernetes operator', 'PostgreSQL (default)', operator_postgres, 'postgresql'),
    ('Kubernetes operator', 'init-projects container image', operator_init_os, 'os'),
]

_eol_cache = {}


def support_status(product, version):
    """Return (state, text), where state is 'ok', 'soon', 'eol' or 'unknown'."""
    if not product:
        return 'unknown', ''
    if product == 'os':
        product = os_product(version)
    if product not in _eol_cache:
        _eol_cache[product] = json.loads(fetch(f'https://endoflife.date/api/{product}.json'))
    cycles = _eol_cache[product]
    number = re.match(r'[\d.]+', re.sub(r'^(CentOS Stream|AlmaLinux) ', '', version))
    if not number:
        return 'unknown', ''
    number = number.group(0).rstrip('.')
    # Match the release cycle, e.g. 3.11 for Python 3.11, 8.10 for Redis 8.10.3, or the
    # newest 7.x cycle for a floating "7" tag
    parts = number.split('.')
    candidates = [c for c in cycles if c['cycle'] in ('.'.join(parts[:2]), parts[0])]
    if not candidates and len(parts) == 1:
        # A floating major tag such as Redis "7" means the newest 7.x release
        candidates = [c for c in cycles if c['cycle'].split('.')[0] == parts[0]][:1]
    if not candidates:

        def key(cycle):
            return tuple(int(p) for p in re.findall(r'\d+', cycle)[:2])

        newest = max(cycles, key=lambda c: key(c['cycle']))
        if key('.'.join(parts[:2])) > key(newest['cycle']):
            return 'ok', f'Newer than {newest["cycle"]}, the latest release with support data'
        return 'unknown', 'No support data'
    eol = candidates[0].get('eol')
    if eol is False:
        return 'ok', 'Supported'
    if eol is True:
        return 'eol', 'End of life'
    eol_date = datetime.date.fromisoformat(eol)
    if eol_date < TODAY:
        return 'eol', f'End of life since {eol_date:%B %Y}'
    if eol_date < TODAY + datetime.timedelta(days=183):
        return 'soon', f'End of life in {eol_date:%B %Y}'
    return 'ok', f'Supported until {eol_date:%B %Y}'


def github_link(reference):
    repo, number = reference.split('#')
    return f'<a href="https://github.com/{repo}/pull/{number}">{html.escape(repo.split("/")[1])}#{number}</a>'


def github_api(path):
    return json.loads(fetch(f'https://api.github.com/{path}'))


def belfry_activity():
    """Return (upstream commits included, Belfry commits, merged pull requests, repositories)."""
    upstream = github_api(f'repos/ansible/awx/compare/{UPSTREAM["app"][1]}...{BELFRY_UPSTREAM_BASE}')['ahead_by']
    commits = 0
    for repo, base in BELFRY_REPOS.items():
        if base:
            commits += github_api(f'repos/belfry-project/{repo}/compare/{base}...HEAD')['ahead_by']
        else:
            page = 1
            while batch := github_api(f'repos/belfry-project/{repo}/commits?per_page=100&page={page}'):
                commits += len(batch)
                page += 1
    pulls = github_api('search/issues?q=org:belfry-project+is:pr+is:merged+-author:app/renovate+-author:app/dependabot')['total_count']
    return upstream, commits, pulls, len(BELFRY_REPOS)


def vulnerability_section():
    """Render the vulnerability comparison from scan-summary.json, or nothing if no scan ran."""
    path = os.path.join(os.path.dirname(__file__), 'scan-summary.json')
    if not os.path.exists(path):
        return '', None
    with open(path, encoding='utf-8') as f:
        summary = json.load(f)

    def cell(result):
        counts, fixable = result['counts'], result['fixable']
        serious = counts['CRITICAL'] + counts['HIGH']
        serious_fixable = fixable['CRITICAL'] + fixable['HIGH']
        return (
            f'<td><span class="version">{serious:,}</span>'
            f'<span class="detail">{counts["CRITICAL"]:,} critical, {counts["HIGH"]:,} high; '
            f'{serious_fixable:,} with a fix available</span></td>'
        )

    rows = []
    totals = [0, 0]
    for item in summary['images']:
        for side, key in enumerate(('awx', 'belfry')):
            totals[side] += item[key]['counts']['CRITICAL'] + item[key]['counts']['HIGH']
        rows.append(
            f'<tr><th scope="row">{html.escape(item["component"])}<span class="detail">{html.escape(item["awx"]["image"])}<br>'
            f'{html.escape(item["belfry"]["image"])}</span></th>{cell(item["awx"])}{cell(item["belfry"])}</tr>'
        )
    section = f"""<h2 id="vulnerabilities">Known vulnerabilities</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th scope="col">Image</th><th scope="col">AWX 24.6.1</th><th scope="col">{BELFRY_LABEL}</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </div>
  <p class="note">Critical and high vulnerabilities found by <a href="https://trivy.dev">Trivy</a> {html.escape(summary['trivy'])}
  (vulnerability database of {html.escape(summary['database'])}), scanned on {html.escape(summary['scanned'])}, for linux/amd64.
  Each vulnerability is counted once per affected package. A finding does not always mean the software can be attacked through it,
  but every one with a fix available can be removed by updating. Run <code>trivy image &lt;image&gt;</code> to reproduce.</p>"""
    return section, totals


def render():
    rows_html = []
    current_group = None
    counts = {'eol': [0, 0], 'soon': [0, 0]}
    for group, component, extractor, product in ROWS:
        if group != current_group:
            rows_html.append(f'<tr class="group"><th colspan="3" scope="colgroup">{html.escape(group)}</th></tr>')
            current_group = group
        cells = []
        for side, refs in enumerate((UPSTREAM, BELFRY)):
            version = extractor(refs)
            state, text = support_status(product, version)
            if state in counts:
                counts[state][side] += 1
            badge = f'<span class="badge {state}">{html.escape(text)}</span>' if text else ''
            cells.append(f'<td><span class="version">{html.escape(version)}</span>{badge}</td>')
        rows_html.append(f'<tr><th scope="row">{html.escape(component)}</th>{"".join(cells)}</tr>')

    with open(os.path.join(os.path.dirname(__file__), 'changes.yml'), encoding='utf-8') as f:
        data = yaml.safe_load(f)
    sections = []
    for category in data['categories']:
        items = [c for c in data['changes'] if c['category'] == category['id']]
        if not items:
            continue
        entries = []
        for change in items:
            links = ' '.join(
                [github_link(link) for link in change.get('links', [])]
                + [f'<a href="{html.escape(u["url"])}">{html.escape(u["title"])}</a>' for u in change.get('urls', [])]
            )
            links_html = f'<p class="links">{links}</p>' if links else ''
            # Merged on main but not in the release the table compares; remove the flag when it is released
            pending = (
                f' <span class="badge soon">Not in {html.escape(BELFRY_LABEL)}: on main, in the next release</span>'
                if change.get('unreleased') and BELFRY_REF != 'main'
                else ''
            )
            entries.append(f'<li><h4>{html.escape(change["title"])}{pending}</h4><p>{html.escape(change["description"])}</p>{links_html}</li>')
        sections.append(f'<section><h3>{html.escape(category["title"])}</h3><ul class="changes">{"".join(entries)}</ul></section>')

    upstream_commits, belfry_commits, belfry_pulls, belfry_repos = belfry_activity()
    vulnerabilities, vulnerability_totals = vulnerability_section()
    vulnerability_stats = ''
    if vulnerability_totals:
        vulnerability_stats = (
            f'<div class="stat"><div class="value">{vulnerability_totals[0]:,} → {vulnerability_totals[1]:,}</div>'
            '<div class="label">critical and high vulnerabilities, AWX 24.6.1 → Belfry, across the three images</div></div>'
        )
    with open(os.path.join(os.path.dirname(__file__), 'template.html'), encoding='utf-8') as f:
        template = f.read()
    return (
        template.replace('{{ rows }}', '\n'.join(rows_html))
        .replace('{{ changes }}', '\n'.join(sections))
        .replace('{{ vulnerabilities }}', vulnerabilities)
        .replace('{{ vulnerability_stats }}', vulnerability_stats)
        .replace('{{ eol_upstream }}', str(counts['eol'][0]))
        .replace('{{ eol_belfry }}', str(counts['eol'][1]))
        .replace('{{ upstream_commits }}', f'{upstream_commits:,}')
        .replace('{{ belfry_commits }}', f'{belfry_commits:,}')
        .replace('{{ belfry_pulls }}', f'{belfry_pulls:,}')
        .replace('{{ belfry_repos }}', str(belfry_repos))
        .replace('{{ generated }}', f'{TODAY:%d %B %Y}')
        .replace('{{ belfry_label }}', BELFRY_LABEL)
    )


if __name__ == '__main__':
    os.makedirs('_site', exist_ok=True)
    with open('_site/index.html', 'w', encoding='utf-8') as f:
        f.write(render())
    print('Wrote _site/index.html')
