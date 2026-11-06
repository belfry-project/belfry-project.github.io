# Belfry

**Belfry** is a community continuation of [AWX](https://github.com/ansible/awx): a web UI, REST API and task engine for running Ansible automation at scale, with a Kubernetes operator to deploy it. These guides are for people who know AWX and want to install Belfry or move an existing AWX installation to it.

<div class="grid cards" markdown>

- **[Install Belfry](install.md)** on Kubernetes with the operator manifests or the Helm chart.
- **[Migrate from AWX](migrate.md)** {{ awx.version }} (awx-operator {{ awx.operator_version }}) to Belfry, in place, with a backup to fall back on.
- **[Belfry vs AWX](https://belfry-project.github.io/)**: every component version and change compared with the last AWX release.
- **[Belfry manual](https://belfry-project.github.io/docs/belfry/)** and **[operator reference](https://belfry-project.github.io/docs/operator/)**: the AWX documentation, published for Belfry.

</div>

## What Belfry is

Upstream AWX releases have been paused since AWX 24.6.1 and awx-operator 2.19.1, in July 2024. Development continued on AWX's `devel` branch, but none of it was released, and the released versions run end-of-life software (Python 3.9 and ansible-core 2.15 in the execution environment, among others).

Belfry continues from AWX's development branch as of November 2026, with all its unreleased fixes, and adds:

- releases with [semantic versioning](releases.md), starting at **{{ release.version }}**;
- current, supported components: Python, Django, ansible-core {{ release.ansible_core }}, Redis 8 and, from the next release, [AlmaLinux 10](faq.md#why-almalinux) as the base of every image;
- images built and published entirely on GitHub, for amd64 and arm64, with [build provenance and SBOMs](verify-images.md), and a daily scan for known vulnerabilities;
- a [tested migration path](migrate.md) from AWX {{ awx.version }}.

Belfry is an independent project. It is not affiliated with, endorsed by or sponsored by Red Hat, Inc. or the Ansible project. AWX, Ansible and Ansible Tower are trademarks of Red Hat, Inc. Belfry keeps the full history and licenses of the projects it is based on.

## What stays compatible

Belfry keeps AWX's interfaces, so existing automation, scripts and Kubernetes resources keep working:

| What | In Belfry |
|---|---|
| REST API | Same paths (`/api/v2/...`), same objects and fields |
| Ansible collection | `awx.awx`, published on the [belfry GitHub releases](https://github.com/belfry-project/belfry/releases) |
| CLI | `awxkit` (the `awx` command), published on the [belfry GitHub releases](https://github.com/belfry-project/belfry/releases) |
| Kubernetes resources | Kinds `AWX`, `AWXBackup`, `AWXRestore` and `AWXMeshIngress`, API group `awx.ansible.com`, version `v1beta1` |
| Operator objects | Namespace and names such as `awx-operator-controller-manager`, the `<name>-web` and `<name>-task` deployments, `<name>-admin-password` and the other secrets |
| Managed execution environment | Still called `AWX EE (latest)`, now pointing to `ghcr.io/belfry-project/belfry-ee` |
| Database | PostgreSQL 15, migrated in place by the usual Django migrations |

## What is different

| What | AWX {{ awx.version }} | Belfry |
|---|---|---|
| Images | `quay.io/ansible/awx`, `awx-ee`, `awx-operator` | `ghcr.io/belfry-project/belfry`, `belfry-ee`, `belfry-operator` |
| Name and logo | AWX | Belfry (the AWX logo is a Red Hat trademark) |
| Versions | 24.6.1 / 2.19.1 | {{ release.version }}, the same version for the application, EE and operator |
| ansible-core in the EE | {{ awx.ansible_core }} | {{ release.ansible_core }} (see [Execution environments](execution-environments.md)) |
| Redis | 7 | 8 |
| Operator metrics | `kube-rbac-proxy` sidecar | Built-in authenticated metrics endpoint |
| Distribution | Quay, Galaxy, PyPI | GitHub only: ghcr.io, GitHub Releases, GitHub Pages |

The [comparison page](https://belfry-project.github.io/) lists every component version, its support status, and every change with a link to the pull request that made it.

## Where to get help

- Questions and bugs: open an issue in the [belfry repository](https://github.com/belfry-project/belfry/issues) (or [belfry-operator](https://github.com/belfry-project/belfry-operator/issues) for the operator).
- Vulnerabilities: report them privately, see [Security](security.md).
- These guides: [edit them on GitHub](https://github.com/belfry-project/belfry-project.github.io/tree/main/docs) with the pencil icon at the top of each page.
