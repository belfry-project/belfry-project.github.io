# Upgrading Belfry

A Belfry upgrade works like an awx-operator upgrade: you install the new belfry-operator release, and it upgrades every `AWX` resource in its namespace to the Belfry version it was released with.

## Before you upgrade

1. Read the [release notes](https://github.com/belfry-project/belfry/releases) of every release between yours and the new one. Breaking changes are only made in a new major version, see [Releases and support](releases.md).
2. [Take a backup](backup-restore.md#taking-a-backup).
3. Check that your `AWX` resource does not pin `image` and `image_version`, unless you want to upgrade them yourself.

Each release of belfry, belfry-ee and belfry-operator has the same version number, and the operator of a release deploys the application and EE images of that release.

## Upgrade the operator

=== "Release manifest"

    ```bash
    kubectl apply --server-side -f https://github.com/belfry-project/belfry-operator/releases/download/<version>/belfry-operator.yaml
    ```

=== "Kustomize"

    Change the `ref` and `newTag` in your `kustomization.yaml` to the new version, then:

    ```bash
    kubectl apply -k .
    ```

=== "Helm"

    Apply the CRDs first ([why](#helm)), then upgrade the chart:

    ```bash
    kubectl apply --server-side --force-conflicts \
      -k "https://github.com/belfry-project/belfry-operator/config/crd?ref=<version>"
    helm repo update
    helm upgrade belfry-operator {{ release.helm_repo_name }}/{{ release.helm_chart }} -n awx --version <chart version> -f values.yaml
    ```

### Helm and CRDs { #helm }

Helm installs the CRDs from the chart's `crds/` directory on `helm install`, but never updates them on `helm upgrade`. Apply them from the operator release before every chart upgrade, as above. `--force-conflicts` takes over the fields that Helm set.

## Watch the upgrade

Then watch the upgrade:

```bash
kubectl -n awx rollout status deployment/awx-operator-controller-manager
kubectl -n awx get pods,jobs -w
kubectl -n awx get awx -o custom-columns=NAME:.metadata.name,VERSION:.status.version,FROM:.status.upgradedFrom
```

The operator runs the database migrations in a Job (`<name>-migration-<hash>`) before it rolls out the new web and task pods.

## PostgreSQL 18 { #postgresql-18 }

belfry-operator {{ release.version }}, like awx-operator {{ awx.operator_version }}, runs the managed database on PostgreSQL 15 (`quay.io/sclorg/postgresql-15-c9s`). From the next release, it runs it on **PostgreSQL 18** (`quay.io/sclorg/postgresql-18-c10s`). PostgreSQL 15 gets fixes until November 2027, PostgreSQL 18 until November 2030, so the move gives Belfry three more years on a supported database, and the newer planner and I/O improvements.

The operator migrates each instance once, during its first reconciliation after the operator upgrade, the same way awx-operator moved from PostgreSQL 13 to 15:

1. It scales down the web and task deployments. **Belfry is unavailable until the migration is done**, which takes about as long as a dump and restore of your database.
2. It creates the StatefulSet `<name>-postgres-18` with a **new PVC** `postgres-18-<name>-postgres-18-0`, of the size and storage class in your `AWX` resource (`postgres_storage_requirements`, `postgres_storage_class`).
3. It copies the data from the old database with `pg_dump` and `pg_restore`, and points `<name>-postgres-configuration` to the new database.
4. It removes the old StatefulSet, Service and NetworkPolicy (`<name>-postgres-15`), sets `status.upgradedPostgresVersion` to `18`, and starts Belfry again.

What you need to do:

- [Take a backup](backup-restore.md#taking-a-backup) first, as for every upgrade.
- Make sure the cluster can provision **a second database volume of the same size**. The old PVC `postgres-15-<name>-postgres-15-0` is kept, so you can go back to it; delete it when the new version works:

    ```bash
    kubectl -n awx delete pvc postgres-15-awx-postgres-15-0
    ```

- If your `AWX` resource sets `postgres_image` or `postgres_image_version`, remove them (or point them to a PostgreSQL 18 image) before upgrading. Otherwise the operator migrates into your PostgreSQL 15 image.
- **External databases** (a `postgres_configuration_secret` of type `unmanaged`) are not touched. Upgrade them when it suits you; Belfry needs PostgreSQL 12 or newer, and is tested with PostgreSQL 18.

Check the result:

```bash
kubectl -n awx get awx awx -o jsonpath='{.status.upgradedPostgresVersion}{"\n"}'
kubectl -n awx exec awx-postgres-18-0 -- psql -tAc 'SHOW server_version'
```

Backups made from PostgreSQL 15, by belfry-operator {{ release.version }} or by awx-operator, restore into a PostgreSQL 18 database. The [upgrade test](migrate.md#what-the-upgrade-test-covers) checks the migration from AWX {{ awx.version }} and from belfry-operator {{ release.version }}, and backups and restores on both versions.

## Upgrading instances one at a time

With `auto_upgrade: false` in an `AWX` resource, the operator leaves a running instance alone. To upgrade it later, set `auto_upgrade: true`, wait for the upgrade, and set it back. See [auto upgrade](https://belfry-project.github.io/docs/operator/user-guide/advanced-configuration/auto-upgrade.html) in the operator reference.

## Following `main`

The `:main` images are built from every commit on `main`. They are for testing and development, not for production: they can contain unreleased database migrations, and there is no supported way back to a release from them. To try them, deploy an operator built from `main` (`?ref=main` and `newTag: main` in Kustomize), which deploys `ghcr.io/belfry-project/belfry:main`.
