# FAQ

## Is Belfry a fork of AWX?

It continues AWX: the repositories are copies of the AWX repositories, with their full history, from AWX's development branch as of November 2026. That branch contains more than two years of development that AWX never released. Belfry is maintained independently, and is not affiliated with Red Hat or the Ansible project.

## Why is it not called AWX?

AWX, Ansible and the AWX logo are trademarks of Red Hat. A project that is not Red Hat's cannot release software under that name. *Belfry* is a bell tower, a nod to Ansible Tower, where AWX comes from.

## Why do I still see "AWX" everywhere?

For compatibility, Belfry keeps AWX's internal names: the `AWX` resource kind and the `awx.ansible.com` API group, the `awx-...` object names, the `awx.awx` collection, the `awx` CLI command, the Python package, the API paths and the managed EE name `AWX EE (latest)`. Renaming them would break existing installations, playbooks and scripts. Only user-facing names and the logo have changed.

## Will my playbooks, `awx.awx` modules and API scripts keep working?

The API is the same, so scripts and the `awx.awx` collection keep working. Playbooks run in a newer ansible-core ({{ release.ansible_core }} instead of {{ awx.ansible_core }}), which can need changes: see the [porting guides](migrate.md#7-update-execution-environments-and-playbooks). You can keep an older EE for playbooks that are not ported yet.

## Can I go back to AWX after migrating?

Only by restoring the backup you took before migrating, with awx-operator. See [Rolling back](migrate.md#rolling-back). Changes made in Belfry after the migration are then lost.

## Does Belfry work without Kubernetes?

Like AWX, Belfry is only supported on Kubernetes, with the operator. The `docker-compose` environment is for development only, see [Contributing](contributing.md).

## Can I run Belfry and AWX in the same cluster?

In different namespaces, yes. Both operators manage the same resource kinds, so do not run both in the same namespace. The CRDs are cluster-wide and shared: belfry-operator's CRDs add fields and a few validations to those of awx-operator {{ awx.operator_version }}, so AWX keeps working with them (one validation: `image` and `image_version` must be set together, or neither).

## Why AlmaLinux 10 and not CentOS? { #why-almalinux }

Since 1.1.0, the Belfry application image, belfry-ee and the operator's init-projects container are built on [AlmaLinux 10](https://almalinux.org/), and Belfry runs on Python 3.14. Belfry 1.0.0 used CentOS Stream 9 for the application and the init-projects container, CentOS Stream 10 for belfry-ee, and Python 3.12; AWX uses CentOS Stream 9.

- **Stable instead of rolling.** CentOS Stream is the preview of the next RHEL minor release: packages land there before RHEL has released them, and there are no point releases to pin or test against. AlmaLinux 10 is a free rebuild of RHEL 10, with point releases and security errata.
- **Longer support.** AlmaLinux 10 is supported until May 2035. CentOS Stream 9, which AWX uses, ends in May 2027, and CentOS Stream 10 around May 2030.
- **The same packages as RHEL.** Package names and `dnf` work as on RHEL and CentOS, so Belfry's images keep AWX's structure, and your execution environments built on belfry-ee install system packages as before, including from EPEL.
- **Free and redistributable,** with official images on quay.io (`quay.io/almalinuxorg/almalinux`).

We also considered Rocky Linux 10 (technically equivalent), Red Hat UBI 10 (its free repositories lack packages Belfry needs to build), Debian or Ubuntu (a rewrite of the images without a gain for users), and minimal images such as Alpine (no rsyslog or nginx, and Python packages built for glibc do not work). The decision is recorded in [DECISIONS.md](https://github.com/belfry-project/.github/blob/main/DECISIONS.md).

The PostgreSQL image of the managed database is not Belfry's own: it is `quay.io/sclorg/postgresql-18-c10s` from the Software Collections project, built on CentOS Stream 10, like the PostgreSQL 15 image before it. There is no AlmaLinux PostgreSQL image with the same layout, and the operator's database migration depends on that layout. The image runs only PostgreSQL, from the same packages RHEL 10 ships. See [PostgreSQL 18](upgrade.md#postgresql-18).

Python 3.14 is the newest Python in AlmaLinux 10, supported upstream until October 2030; AWX {{ awx.version }} runs on Python 3.11.

## Which UI does Belfry use?

The Ansible UI that AWX's development branch uses ([belfry-ui](https://github.com/belfry-project/belfry-ui)), built from ansible-ui as of September 2024.

## Where are the collection and CLI?

On the [belfry GitHub releases](https://github.com/belfry-project/belfry/releases), not on Galaxy or PyPI:

```bash
ansible-galaxy collection install https://github.com/belfry-project/belfry/releases/download/{{ release.version }}/awx-awx-{{ release.version }}.tar.gz
pip install https://github.com/belfry-project/belfry/releases/download/{{ release.version }}/awxkit-{{ release.version }}-py3-none-any.whl
```

## Is it free?

Yes. Belfry is under the same licenses as AWX (Apache 2.0 for most of it). All images, charts and docs are public.

## How can I help?

Try the migration and report how it went, report bugs, or send a pull request. See [Contributing](contributing.md).
