#!/usr/bin/env python3
"""Scan the AWX and Belfry images for known vulnerabilities with Trivy.

Writes scan-summary.json, which build.py adds to the comparison page. Run with
the trivy binary on PATH (or set TRIVY).
"""

import datetime
import json
import os
import subprocess

# (component, AWX image as released, Belfry image)
IMAGES = [
    ('Application', 'quay.io/ansible/awx:24.6.1', 'ghcr.io/belfry-project/belfry:latest'),
    ('Execution environment', 'quay.io/ansible/awx-ee:24.6.1', 'ghcr.io/belfry-project/belfry-ee:latest'),
    ('Kubernetes operator', 'quay.io/ansible/awx-operator:2.19.1', 'ghcr.io/belfry-project/belfry-operator:latest'),
]
SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
TRIVY = os.environ.get('TRIVY', 'trivy')


def scan(image):
    """Return vulnerability counts for one image (linux/amd64), counting each CVE once per package."""
    result = subprocess.run(
        [TRIVY, 'image', '--quiet', '--scanners', 'vuln', '--platform', 'linux/amd64', '--format', 'json', image],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    seen = set()
    counts = {s: 0 for s in SEVERITIES}
    fixable = {s: 0 for s in SEVERITIES}
    for target in report.get('Results') or []:
        for vuln in target.get('Vulnerabilities') or []:
            key = (vuln['VulnerabilityID'], vuln['PkgName'], vuln.get('InstalledVersion'))
            if key in seen or vuln.get('Severity') not in counts:
                continue
            seen.add(key)
            counts[vuln['Severity']] += 1
            if vuln.get('FixedVersion'):
                fixable[vuln['Severity']] += 1
    return {
        'image': image,
        'digest': (report.get('Metadata') or {}).get('RepoDigests', [None])[0],
        'counts': counts,
        'fixable': fixable,
    }


def main():
    version = json.loads(subprocess.run([TRIVY, 'version', '--format', 'json'], check=True, capture_output=True, text=True).stdout)
    summary = {
        'scanned': datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M UTC'),
        'trivy': version.get('Version'),
        'database': (version.get('VulnerabilityDB') or {}).get('UpdatedAt', '')[:10],
        'images': [],
    }
    for component, upstream, belfry in IMAGES:
        print(f'Scanning {upstream} and {belfry}')
        summary['images'].append({'component': component, 'awx': scan(upstream), 'belfry': scan(belfry)})
    with open('scan-summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print('Wrote scan-summary.json')


if __name__ == '__main__':
    main()
