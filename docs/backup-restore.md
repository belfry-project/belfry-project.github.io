# Backup and restore

Backups work as with awx-operator, with the same `AWXBackup` and `AWXRestore` resources. A backup contains the PostgreSQL database dump **and** the secrets that go with it (the secret key that encrypts credentials, the admin password, the PostgreSQL configuration, receptor certificates), and the spec of the `AWX` resource. Both are needed to restore: a database dump without the secret key cannot decrypt your credentials.

## Taking a backup

```yaml title="awxbackup.yaml"
apiVersion: awx.ansible.com/v1beta1
kind: AWXBackup
metadata:
  name: awx-backup-2026-11-05
  namespace: awx
spec:
  deployment_name: awx
  # Optional:
  # backup_storage_class: standard
  # backup_storage_requirements: 20Gi
  # use_db_compression: true
```

```bash
kubectl apply -f awxbackup.yaml
kubectl -n awx get awxbackup awx-backup-2026-11-05 -o jsonpath='{.status}{"\n"}'
```

The backup is done when the status shows `backupDirectory` (and `backupClaim`, the PVC it is in). By default the operator creates a PVC `<backup name>-claim`. Use `backup_pvc` for an existing PVC, for example one shared by all backups.

Deleting the `AWXBackup` resource keeps the backup data, unless you set `clean_backup_on_delete: true`. Deleting the namespace deletes the PVC too.

For scheduled backups, create `AWXBackup` resources from a CronJob, or with your GitOps tool. All fields are in the [operator reference](https://belfry-project.github.io/docs/operator/), and in the CRD:

```bash
kubectl explain awxbackup.spec
```

## Copying a backup off the cluster

A backup in a PVC in the same namespace does not protect you against losing the cluster or the namespace. Copy it somewhere else, for example with a temporary pod that mounts the backup PVC:

```bash
kubectl -n awx run backup-copy --restart=Never --image=busybox --overrides='
{"spec": {"containers": [{"name": "backup-copy", "image": "busybox", "command": ["sleep", "3600"],
  "volumeMounts": [{"name": "backup", "mountPath": "/backups"}]}],
  "volumes": [{"name": "backup", "persistentVolumeClaim": {"claimName": "awx-backup-2026-11-05-claim"}}]}}'
kubectl -n awx wait pod/backup-copy --for=condition=Ready
kubectl -n awx cp backup-copy:/backups ./awx-backups
kubectl -n awx delete pod backup-copy
```

## Restoring

Restore into a **new** instance name, or delete the existing instance first. Even under a new name, the restored instance uses some of the original secret names (`<original>-admin-password`, `<original>-secret-key`, `<original>-broadcast-websocket`), and the restore overwrites them with the backed-up values, which is harmless for a backup of the same instance. The admin password is the one from the backup: read it from the secret named in `status.adminPasswordSecret` of the restored `AWX` resource. When you delete an `AWX` resource, the operator keeps its secrets, and the PostgreSQL PVC stays too; delete them if you restore under the same name, so that the restore recreates them from the backup:

```bash
kubectl -n awx delete awx awx --wait
kubectl -n awx delete secret --ignore-not-found awx-admin-password awx-secret-key \
  awx-broadcast-websocket awx-postgres-configuration awx-receptor-ca awx-receptor-work-signing
kubectl -n awx delete pvc --ignore-not-found postgres-15-awx-postgres-15-0 postgres-18-awx-postgres-18-0
```

The PVC is `postgres-15-...` in {{ release.version }} and `postgres-18-...` from the next release, which moves the managed database to [PostgreSQL 18](upgrade.md#postgresql-18). A backup made from PostgreSQL 15 restores into PostgreSQL 18.

```yaml title="awxrestore.yaml"
apiVersion: awx.ansible.com/v1beta1
kind: AWXRestore
metadata:
  name: awx-restore
  namespace: awx
spec:
  deployment_name: awx          # the instance to create
  backup_name: awx-backup-2026-11-05
```

```bash
kubectl apply -f awxrestore.yaml
kubectl -n awx get awxrestore awx-restore -o jsonpath='{.status}{"\n"}'
```

The restore is done when the status shows `restoreComplete: true`. The operator then creates the `AWX` resource with the spec from the backup, and starts it. If the backup comes from an older version (also an AWX {{ awx.version }} backup), the operator migrates the restored database to its Belfry version with a migration Job, as in an upgrade.

To restore from a backup that is not an `AWXBackup` resource any more, set `backup_pvc` and `backup_dir` instead of `backup_name`.

!!! note "Tested"
    The [upgrade test](migrate.md#what-the-upgrade-test-covers) backs up AWX {{ awx.version }} with awx-operator {{ awx.operator_version }}, restores it with belfry-operator into a new instance, and checks the data, the credential secrets and a new job there ([belfry-operator#17](https://github.com/belfry-project/belfry-operator/pull/17)).

    Use a belfry-operator release that includes [#23](https://github.com/belfry-project/belfry-operator/pull/23) and [#25](https://github.com/belfry-project/belfry-operator/pull/25), which every release does: without #23, backup and restore pods could not reach the managed PostgreSQL on clusters that enforce NetworkPolicies, and without #25 a restore left empty `<new instance>-admin-password` and similar secrets.
