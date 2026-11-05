# Migrating from AWX to Belfry

This guide moves an existing AWX installation on Kubernetes to Belfry **in place**: you replace awx-operator with belfry-operator, and it upgrades the same `AWX` resource, database and secrets to Belfry. Your organizations, inventories, credentials, projects, templates, job history and cached facts stay.

It takes about as long as an AWX upgrade: the web and task pods are replaced and the database is migrated, so plan a short maintenance window. Running jobs are interrupted.

!!! success "Tested every week"
    The steps below follow the automated [upgrade test](#what-the-upgrade-test-covers), which installs AWX {{ awx.version }} with awx-operator {{ awx.operator_version }}, creates data, switches to belfry-operator and checks the result. Steps the test does not cover are marked **Not covered by the upgrade test**.

## Overview

1. [Check the prerequisites](#1-check-the-prerequisites)
2. [Take a backup](#2-take-a-backup) with awx-operator, and keep it
3. [Check your `AWX` resource](#3-check-your-awx-resource) for pinned images
4. [Switch the operator](#4-switch-the-operator) to belfry-operator
5. [Watch the upgrade](#5-watch-the-upgrade)
6. [Verify](#6-verify) the result
7. [Update execution environments](#7-update-execution-environments-and-playbooks) and playbooks for ansible-core {{ release.ansible_core }}

If something goes wrong: [Roll back](#rolling-back).

## 1. Check the prerequisites

**Versions.** The tested starting point is the last AWX release: **AWX {{ awx.version }} with awx-operator {{ awx.operator_version }}**. Check what you run:

```bash
kubectl -n awx get deployment awx-operator-controller-manager \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="awx-manager")].image}{"\n"}'
kubectl -n awx get awx -o custom-columns=NAME:.metadata.name,VERSION:.status.version
```

The first command should print `quay.io/ansible/awx-operator:{{ awx.operator_version }}`, the second `{{ awx.version }}`.

!!! warning "Older AWX versions"
    Upgrade to AWX {{ awx.version }} with awx-operator {{ awx.operator_version }} first, following the [awx-operator upgrade notes](https://belfry-project.github.io/docs/operator/upgrade/upgrading.html), and check that it works. Then migrate to Belfry. Going directly from older versions is **not covered by the upgrade test**. The database migrations themselves run from any AWX version that awx-operator {{ awx.operator_version }} could upgrade, but older operators had other resource layouts (for example PostgreSQL 13 before awx-operator 2.0, which the operator migrates to PostgreSQL 15).

**Namespace and names.** These commands use the namespace `awx` and an `AWX` resource named `awx`, as in the awx-operator documentation. Replace them with yours. List them with:

```bash
kubectl get awx --all-namespaces
```

**kube-rbac-proxy.** The awx-operator {{ awx.operator_version }} manifests use the sidecar image `gcr.io/kubebuilder/kube-rbac-proxy:v0.15.0`, which **no longer exists**. If your operator pod is running, the image is cached on the node, but a reschedule fails with `ImagePullBackOff`. You need a working awx-operator for the backup (and for a rollback), so if it does not run, replace the image with the same version from quay.io, as the upgrade test does:

```yaml title="kustomization.yaml (awx-operator {{ awx.operator_version }})"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - https://github.com/ansible/awx-operator/config/default?ref={{ awx.operator_version }}
images:
  - name: quay.io/ansible/awx-operator
    newTag: {{ awx.operator_version }}
  - name: gcr.io/kubebuilder/kube-rbac-proxy
    newName: quay.io/brancz/kube-rbac-proxy
    newTag: v0.15.0
namespace: awx
```

Belfry's operator no longer uses kube-rbac-proxy: the metrics endpoint does its own authentication.

**Image access.** The nodes must be able to pull `ghcr.io/belfry-project/belfry`, `belfry-ee` and `belfry-operator`, and `docker.io/redis:8`. For a mirror, see [Execution environments](execution-environments.md#private-registries) and the image fields in the [operator reference](https://belfry-project.github.io/docs/operator/user-guide/advanced-configuration/deploying-a-specific-version-of-awx.html).

## 2. Take a backup

Back up with **awx-operator, before switching**. An `AWXBackup` contains the database dump and the secrets (secret key, admin password, PostgreSQL configuration and the others) that you need to restore it. A database dump alone is not enough.

```yaml title="awxbackup.yaml"
apiVersion: awx.ansible.com/v1beta1
kind: AWXBackup
metadata:
  name: awx-before-belfry
  namespace: awx
spec:
  deployment_name: awx
```

```bash
kubectl apply -f awxbackup.yaml
# Wait until the backup is done (kubectl 1.31 or newer; else repeat the last command)
kubectl -n awx wait awxbackup/awx-before-belfry --for=jsonpath='{.status.backupDirectory}' --timeout=30m
kubectl -n awx get awxbackup awx-before-belfry -o jsonpath='{.status}{"\n"}'
```

The operator creates the PVC `awx-before-belfry-claim` for it, unless you set `backup_pvc`. Keep the `AWXBackup` resource and its PVC until you are sure you do not need to roll back: deleting the namespace deletes them too. Many users also copy the backup off the cluster, see [Backup and restore](backup-restore.md#copying-a-backup-off-the-cluster).

## 3. Check your `AWX` resource

belfry-operator keeps the spec of your `AWX` resource. Fields that pin AWX images would keep AWX running instead of Belfry, so look for them:

```bash
kubectl -n awx get awx awx -o yaml | grep -nE 'image|ee_images|auto_upgrade'
```

- **`image` / `image_version`**: if they point to `quay.io/ansible/awx`, remove both (the operator then deploys the Belfry version it was released with), or set them to `ghcr.io/belfry-project/belfry` and `{{ release.version }}`. Both must be set together, or neither; belfry-operator validates this.
- **`ee_images`, `control_plane_ee_image`, `init_container_image`**: if they point to `quay.io/ansible/awx-ee`, remove them or point them to `ghcr.io/belfry-project/belfry-ee:{{ release.version }}` (or your own EE built on it, see [Execution environments](execution-environments.md)).
- **`redis_image` / `redis_image_version`**: remove them to get Redis 8, or keep your own.
- **`auto_upgrade: false`**: the operator then does not touch a running instance. Set it to `true` for the migration.

To remove a field:

```bash
kubectl -n awx patch awx awx --type=json -p '[{"op":"remove","path":"/spec/image"},{"op":"remove","path":"/spec/image_version"}]'
```

If you manage the resource with Helm or GitOps, change it there instead.

## 4. Switch the operator

Install belfry-operator **over** awx-operator, in the same namespace. It uses the same deployment name (`awx-operator-controller-manager`), CRDs and RBAC names, so the old operator is replaced, not run next to it. Your `AWX`, `AWXBackup` and `AWXRestore` resources stay.

=== "Kustomize (tested)"

    If you installed awx-operator with a `kustomization.yaml` as in its documentation, change the resource URL and the image, and apply it again:

    ```yaml title="kustomization.yaml"
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - https://github.com/belfry-project/belfry-operator/config/default?ref={{ release.version }}
    images:
      - name: ghcr.io/belfry-project/belfry-operator
        newTag: "{{ release.version }}"
    namespace: awx
    ```

    ```bash
    kubectl apply -k .
    kubectl -n awx rollout status deployment/awx-operator-controller-manager --timeout=10m
    ```

    This is what the upgrade test does (with `make deploy`, which applies the same `config/default`). `kubectl apply` also removes the kube-rbac-proxy container from the operator deployment. Two cluster objects of awx-operator are left over and can be deleted:

    ```bash
    kubectl delete clusterrolebinding awx-operator-proxy-rolebinding --ignore-not-found
    kubectl delete clusterrole awx-operator-proxy-role --ignore-not-found
    ```

=== "Release manifest"

    **Not covered by the upgrade test.** Delete the old operator deployment first (this does not touch your AWX instance, it only stops the operator), then apply the belfry-operator manifest:

    ```bash
    kubectl -n awx delete deployment awx-operator-controller-manager
    kubectl apply --server-side --force-conflicts -f {{ release.operator_manifest }}
    kubectl -n awx rollout status deployment/awx-operator-controller-manager --timeout=10m
    ```

    The manifest installs into the namespace `awx`. For another namespace, use the Kustomize way with your `namespace:`.

=== "Helm"

    **Not covered by the upgrade test.** If you installed awx-operator with the [awx-operator-helm](https://github.com/ansible-community/awx-operator-helm) chart, switch the same release to the Belfry chart. The chart uses the same values (`AWX.enabled`, `AWX.name`, `AWX.spec`, ...), so keep your values file, after [checking it](#3-check-your-awx-resource) for pinned images.

    Helm does not update CRDs, so apply the Belfry CRDs first:

    ```bash
    kubectl apply --server-side --force-conflicts \
      -k "https://github.com/belfry-project/belfry-operator/config/crd?ref={{ release.version }}"
    ```

    The label selector of the operator deployment differs between the two charts (`helm.sh/chart: awx-operator` and `belfry-operator`), and selectors cannot be changed, so delete the old operator deployment before the upgrade. This does not touch your AWX instance:

    ```bash
    helm repo add {{ release.helm_repo_name }} {{ release.helm_repo }}
    helm repo update
    kubectl -n awx delete deployment awx-operator-controller-manager
    helm upgrade my-awx-operator {{ release.helm_repo_name }}/{{ release.helm_chart }} \
      --namespace awx --version {{ release.chart_version }} -f myvalues.yaml
    kubectl -n awx rollout status deployment/awx-operator-controller-manager --timeout=10m
    ```

    Use your release name instead of `my-awx-operator` (`helm list -n awx`). If your values file sets `AWX.enabled: true`, Helm keeps managing the same `AWX` resource. Check that it is there with the same name before you continue: if your values file were missing, Helm would delete the resource, and with it your instance.

The new operator image deploys `ghcr.io/belfry-project/belfry:{{ release.version }}` by default. Check that the right operator runs:

```bash
kubectl -n awx get deployment awx-operator-controller-manager \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}: {.image}{"\n"}{end}'
```

It should show one container, `awx-manager: ghcr.io/belfry-project/belfry-operator:{{ release.version }}`.

## 5. Watch the upgrade

The operator reconciles your `AWX` resource within a minute. What happens:

1. The web and task deployments get the Belfry image `ghcr.io/belfry-project/belfry:{{ release.version }}`, the Redis 8 sidecar (`docker.io/redis:8.x`, instead of Redis 7) and init containers from `belfry-ee`. Redis only holds transient data (the websocket and dispatcher queues), so nothing needs to be migrated there.
2. A Job `awx-migration-<hash>` runs the database migrations from AWX {{ awx.version }} to Belfry on the existing PostgreSQL 15 database. PostgreSQL itself is not changed.
3. The task pod registers the managed execution environments: `AWX EE (latest)` now points to `{{ release.latest_ee_image }}`, `AWX EE ({{ release.version }})` (`belfry-ee:{{ release.version }}`) is added, and the Control Plane Execution Environment uses `belfry-ee:{{ release.version }}`. See [step 7](#7-update-execution-environments-and-playbooks) for `AWX EE ({{ awx.version }})`.
4. The `AWX` resource status gets the new `version`, and `upgradedFrom: {{ awx.version }}`.

Follow it:

```bash
kubectl -n awx get pods,jobs -w
kubectl -n awx logs -f deployment/awx-operator-controller-manager -c awx-manager
```

and wait until both deployments run the Belfry image:

```bash
kubectl -n awx rollout status deployment/awx-web --timeout=20m
kubectl -n awx rollout status deployment/awx-task --timeout=20m
kubectl -n awx get deployment awx-web awx-task \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'
```

The operator log shows a summary at the end of every reconcile (`failed=0` means success). If the migration Job fails, see its log with `kubectl -n awx logs job/<name>`, and [open an issue](https://github.com/belfry-project/belfry-operator/issues) with it.

## 6. Verify

```bash
kubectl -n awx get awx awx -o jsonpath='version={.status.version} upgradedFrom={.status.upgradedFrom}{"\n"}'
curl -s https://awx.example.com/api/v2/ping/ | python3 -m json.tool
```

Then log in with the same admin password as before (`awx-admin-password` is unchanged) and check, as the upgrade test does:

- [ ] your organizations, inventories, credentials, projects and templates are there;
- [ ] finished jobs and their output are still there;
- [ ] cached facts of your hosts are still there;
- [ ] a project sync works;
- [ ] a job runs, can use a credential created before the upgrade (the secret key is unchanged, so encrypted fields can still be decrypted), and updates the facts;
- [ ] the job ran in `ghcr.io/belfry-project/belfry-ee` (shown in the job details).

Check what is beyond the test too: your schedules, notifications, authentication (LDAP, SAML, OIDC), container groups and the instances of your execution nodes or hop nodes.

## 7. Update execution environments and playbooks

**ansible-core {{ awx.ansible_core }} to {{ release.ansible_core }}.** The AWX {{ awx.version }} execution environment has ansible-core {{ awx.ansible_core }} on Python 3.9. `belfry-ee` has ansible-core {{ release.ansible_core }} on Python 3.14. This is the largest change for your playbooks: seven ansible-core versions. Read the porting guides:

- [ansible-core 2.16](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.16.html)
- [ansible-core 2.17](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.17.html): drops Python 2.7 and 3.6 on managed nodes
- [ansible-core 2.18](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.18.html)
- [ansible-core 2.19](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.19.html): **data tagging and templating changes**. Templates in conditionals must be expressions, not `{{ '{{ ... }}' }}`; broken or untrusted templates fail instead of being passed through; implicit conversion of strings to booleans in conditionals is deprecated. Most playbook breakage comes from here.
- [ansible-core 2.20](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.20.html)
- [ansible-core 2.21](https://docs.ansible.com/ansible/latest/porting_guides/porting_guide_core_2.21.html)
- [ansible-core 2.22](https://docs.ansible.com/projects/ansible/devel/porting_guides/porting_guide_core_2.22.html)

To test your playbooks before the migration, run them against `ghcr.io/belfry-project/belfry-ee:{{ release.version }}` in AWX {{ awx.version }}: add it as an execution environment and select it in a copy of a job template. It works with AWX {{ awx.version }} too.

**`AWX EE ({{ awx.version }})`** stays registered with its old image `quay.io/ansible/awx-ee:{{ awx.version }}`, and job templates, projects, organizations or inventory sources that select it keep using it. Find them, and switch them to `AWX EE (latest)` or `AWX EE ({{ release.version }})`:

```bash
BELFRY=https://awx.example.com
curl -s -u admin "$BELFRY/api/v2/execution_environments/?image__startswith=quay.io/ansible" | python3 -m json.tool
# for each id found:
curl -s -u admin "$BELFRY/api/v2/unified_job_templates/?execution_environment=<id>" | python3 -m json.tool
curl -s -u admin "$BELFRY/api/v2/organizations/?default_environment=<id>" | python3 -m json.tool
```

Then delete the old execution environment if nothing uses it.

**Custom execution environments.** If you built your own EE on `quay.io/ansible/awx-ee`, rebuild it on `ghcr.io/belfry-project/belfry-ee:{{ release.version }}`, see [Execution environments](execution-environments.md#building-your-own). Your old images keep working in Belfry as long as they have a compatible ansible-runner, but they keep their old ansible-core.

**Collection and CLI.** Install `awx.awx` and `awxkit` from the [belfry releases](https://github.com/belfry-project/belfry/releases). The 24.6.1 versions from Galaxy and PyPI generally keep working against the Belfry API, since the API is the same, but they warn about the version difference and miss newer fields.

## Rolling back

**Not covered by the upgrade test.** A rollback restores the backup from [step 2](#2-take-a-backup) with awx-operator {{ awx.operator_version }}. Everything done in Belfry after the switch is lost. The database cannot be migrated back, so you cannot just reinstall the old operator over the upgraded instance.

1. Delete the Belfry instance, its secrets and its database volume. The operator keeps the secrets when the resource is deleted, and the restore must recreate them from the backup. **Do not delete the namespace**: the backup PVC is in it.

    ```bash
    kubectl -n awx delete awx awx --wait --timeout=10m
    kubectl -n awx delete secret --ignore-not-found awx-admin-password awx-secret-key \
      awx-broadcast-websocket awx-postgres-configuration awx-receptor-ca awx-receptor-work-signing
    kubectl -n awx delete pvc --ignore-not-found postgres-15-awx-postgres-15-0
    ```

2. Reinstall awx-operator {{ awx.operator_version }}, with the [kube-rbac-proxy workaround](#1-check-the-prerequisites):

    ```bash
    kubectl -n awx delete deployment awx-operator-controller-manager
    kubectl apply -k path/to/awx-operator-kustomization/
    ```

3. Restore the backup:

    ```yaml title="awxrestore.yaml"
    apiVersion: awx.ansible.com/v1beta1
    kind: AWXRestore
    metadata:
      name: awx-rollback
      namespace: awx
    spec:
      deployment_name: awx
      backup_name: awx-before-belfry
    ```

    ```bash
    kubectl apply -f awxrestore.yaml
    kubectl -n awx wait awxrestore/awx-rollback --for=jsonpath='{.status.restoreComplete}'=true --timeout=60m
    ```

The restored `AWX` resource gets the spec from the backup, so it runs AWX {{ awx.version }} again.

!!! note "Restoring the AWX backup with belfry-operator"
    You can also restore the AWX {{ awx.version }} backup with **belfry-operator**: the restored instance then runs Belfry, and the operator migrates the restored database with a migration Job. This is how to start over if the in-place switch failed halfway, or how to migrate into a new instance (or another cluster) while the AWX instance keeps running. The restored instance gets the admin password of the AWX instance; read it from the secret named in `status.adminPasswordSecret` of the new `AWX` resource. This path is being added to the upgrade test ([belfry-operator#17](https://github.com/belfry-project/belfry-operator/pull/17)).

## What the upgrade test covers

The workflow [`upgrade-test.yml`](https://github.com/belfry-project/belfry-operator/blob/main/.github/workflows/upgrade-test.yml) in belfry-operator runs every week and on changes to the test, and release workflows can run it for the released images. Its [scripts are in `tests/upgrade/`](https://github.com/belfry-project/belfry-operator/tree/main/tests/upgrade). On a fresh kind cluster, it:

1. installs awx-operator {{ awx.operator_version }} (with the kube-rbac-proxy image from quay.io) and an `AWX` resource without image fields, which runs AWX {{ awx.version }};
2. creates an organization, an inventory with a host, a credential with a secret, a project from Git, a job template, and runs a job that uses the secret and caches facts;
3. backs it up with an `AWXBackup` (being added in [belfry-operator#17](https://github.com/belfry-project/belfry-operator/pull/17));
4. applies belfry-operator's `config/default` over awx-operator (`make deploy`) and waits until the web and task deployments run the Belfry image;
5. checks that the version changed, that all objects, the old job with its output and the cached facts survived, and that a new job runs in `belfry-ee`, decrypts the old credential and updates the facts;
6. being added in [belfry-operator#17](https://github.com/belfry-project/belfry-operator/pull/17): deletes that instance, restores the {{ awx.version }} backup with belfry-operator into a new instance with an `AWXRestore`, checks that the operator ran a migration Job for it, and verifies the same data and a new job there.

[Latest runs](https://github.com/belfry-project/belfry-operator/actions/workflows/upgrade-test.yml).

**Not covered:** the Helm and release-manifest ways of switching, AWX versions before {{ awx.version }}, rolling back with awx-operator, external (unmanaged) PostgreSQL, OpenShift, ingress and routes, LDAP/SAML/OIDC, execution and hop nodes, mesh ingress, custom EEs, multiple instances per namespace, and large databases (the migration of a large job event table takes longer). Please [report](https://github.com/belfry-project/belfry-operator/issues) how your migration went, especially for these.
