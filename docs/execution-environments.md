# Execution environments

Jobs run in an execution environment (EE): a container image with ansible-core, ansible-runner, collections and Python packages. Belfry's default EE is **belfry-ee**, `ghcr.io/belfry-project/belfry-ee`, built from [belfry-project/belfry-ee](https://github.com/belfry-project/belfry-ee) with [ansible-builder](https://ansible-builder.readthedocs.io/).

## What is in belfry-ee

| | AWX EE {{ awx.version }} | belfry-ee |
|---|---|---|
| Base image | CentOS Stream 9 | AlmaLinux 10 (1.0.0: CentOS Stream 10), see [why](faq.md#why-almalinux) |
| Python | 3.9 | 3.14 (`/usr/bin/python3.14`) |
| ansible-core | {{ awx.ansible_core }} | {{ release.ansible_core }} |
| Architectures | amd64, arm64 | amd64, arm64 |

It also contains ansible-runner, receptor, `awxkit`, `ansible-sign`, git, git-lfs, subversion, rsync, sshpass, Kerberos and WinRM/PSRP support, `podman-remote`, and these collections: `awx.awx`, `amazon.aws`, `azure.azcollection`, `google.cloud`, `openstack.cloud`, `community.vmware`, `ovirt.ovirt`, `kubernetes.core`, `kubevirt.core`, `ansible.posix`, `ansible.windows`, `theforeman.foreman` and `redhatinsights.insights`. The exact definition is [`execution-environment.yml`](https://github.com/belfry-project/belfry-ee/blob/main/execution-environment.yml); the exact versions of every package are in the image's [SBOM](verify-images.md#sboms).

Tags: `:{{ release.version }}` for a release, `:latest` for the newest release, `:main` for the newest build of `main` (see [Releases and support](releases.md#image-tags)).

The operator registers two EEs for it, and uses `belfry-ee:<version>` as the Control Plane Execution Environment (for project updates and inventory syncs):

- `AWX EE (<version>)`, e.g. `AWX EE ({{ release.version }})`: `belfry-ee:<version>`, the EE released with your Belfry version. Select it for reproducible jobs.
- `AWX EE (latest)`: `{{ release.latest_ee_image }}`, the EE of the installed Belfry release. Unlike AWX's rolling `awx-ee:latest`, it only changes when you upgrade Belfry. The name stays, so job templates that use it keep working.

## Building your own

Build your EE **on top of belfry-ee**, so you get its Python, ansible-core and runner, and only add what you need. Install [ansible-builder](https://ansible-builder.readthedocs.io/en/stable/installation/) 3, then:

```yaml title="execution-environment.yml"
version: 3
images:
  base_image:
    name: ghcr.io/belfry-project/belfry-ee:{{ release.version }}
dependencies:
  # belfry-ee uses Python 3.14, which is not the default python3 of
  # AlmaLinux 10. Without this, Python packages would be installed for the
  # wrong Python.
  python_interpreter:
    python_path: /usr/bin/python3.14
  galaxy:
    collections:
      - name: community.general
      - name: community.postgresql
  python:
    - psycopg2-binary
  system:
    - openldap-clients [platform:rpm]
```

```bash
ansible-builder build -t registry.example.com/automation/my-ee:1.0 -f execution-environment.yml
podman push registry.example.com/automation/my-ee:1.0
```

Then add it in Belfry under **Administration > Execution Environments**, or in the `AWX` resource with `ee_images`. Pin the base image to a release tag (or a digest) rather than `:latest`, so a rebuild does not change ansible-core under you.

Check what ended up in the image:

```bash
podman run --rm registry.example.com/automation/my-ee:1.0 ansible --version
podman run --rm registry.example.com/automation/my-ee:1.0 ansible-galaxy collection list
```

### Moving an existing EE from awx-ee

If your EE is built `FROM quay.io/ansible/awx-ee`, change the base image to `ghcr.io/belfry-project/belfry-ee:{{ release.version }}` and add the `python_interpreter` above. Python packages built for Python 3.9 must be reinstalled for 3.14, which ansible-builder does on the rebuild. Then test your playbooks against ansible-core {{ release.ansible_core }}, see the [porting guides](migrate.md#7-update-execution-environments-and-playbooks).

## Older execution environments

EEs with older ansible-core versions keep working in Belfry: the EE only needs a compatible ansible-runner. This lets you move job templates to the new EE one at a time.

!!! note "Fact cache and ansible-core 2.19"
    ansible-core 2.19 changed the format in which facts are cached. AWX {{ awx.version }} could not read it: with a newer EE, jobs did not see cached facts, and facts were cleared after every job. Belfry reads and writes both formats ([belfry#18](https://github.com/belfry-project/belfry/pull/18)), so fact caching works with EEs on both sides of 2.19. Facts cached by AWX are kept when you migrate.

## Private registries

To pull EEs from a private registry, create a **Container Registry** credential and select it in the execution environment. For the default EEs, the operator can do this for you: see `ee_pull_credentials_secret` in [deploying a specific version](https://belfry-project.github.io/docs/operator/user-guide/advanced-configuration/deploying-a-specific-version-of-awx.html) in the operator reference. To mirror belfry-ee, copy it with all architectures, for example:

```bash
skopeo copy --all docker://ghcr.io/belfry-project/belfry-ee:{{ release.version }} docker://registry.example.com/belfry/belfry-ee:{{ release.version }}
```

and set `ee_images` and `control_plane_ee_image` in the `AWX` resource to the mirrored image.
