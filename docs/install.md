# Installing on Kubernetes

Belfry runs on Kubernetes and is managed by **belfry-operator**: you install the operator, then create an `AWX` resource, and the operator deploys Belfry, its PostgreSQL database and everything else. This is the same model as awx-operator, with the same resource kinds.

!!! tip "Moving from AWX?"
    Do not install Belfry next to an existing AWX: follow [Migrating from AWX](migrate.md) instead, which switches your existing installation in place.

## Requirements

- A Kubernetes cluster that is still supported upstream, on amd64 or arm64 nodes. The operator's tests run on [kind](https://kind.sigs.k8s.io/); OpenShift works as with awx-operator.
- For a small instance, at least 2 CPUs and 4 GB of memory available, more for real workloads.
- A default StorageClass, for the PostgreSQL volume (or bring your own database, see the [operator reference](https://belfry-project.github.io/docs/operator/user-guide/database-configuration.html)).
- `kubectl` with access to the cluster, and [Helm](https://helm.sh/) 3 if you use the chart.
- The nodes need to pull from `ghcr.io` (Belfry, the operator and the execution environment), `docker.io` (Redis) and `quay.io` (PostgreSQL, and the init image for persistent projects: AlmaLinux 10 minimal). For disconnected clusters, mirror those images and set the image fields of the `AWX` resource.

All commands below use the namespace `awx`, like awx-operator. You can choose another one.

## 1. Install the operator

Choose one of the three ways. They install the same operator.

=== "Release manifest"

    Every belfry-operator release has a single manifest attached to its [GitHub release](https://github.com/belfry-project/belfry-operator/releases), with the CRDs, RBAC and the operator deployment in the namespace `awx`:

    ```bash
    kubectl apply --server-side -f {{ release.operator_manifest }}
    kubectl -n awx rollout status deployment/awx-operator-controller-manager
    ```

=== "Kustomize"

    Create a `kustomization.yaml` that points to a release tag. This is the way the awx-operator documentation describes, so existing setups only need the URL and image changed:

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
    kubectl -n awx rollout status deployment/awx-operator-controller-manager
    ```

=== "Helm"

    The chart is published in the Belfry Helm repository:

    ```bash
    helm repo add {{ release.helm_repo_name }} {{ release.helm_repo }}
    helm repo update
    helm install belfry-operator {{ release.helm_repo_name }}/{{ release.helm_chart }} \
      --namespace awx --create-namespace --version {{ release.chart_version }}
    kubectl -n awx rollout status deployment/awx-operator-controller-manager
    ```

    The chart can also create the `AWX` resource for you, from your values file. It uses the same values as the awx-operator-helm chart:

    ```yaml title="values.yaml"
    AWX:
      enabled: true
      name: awx
      spec:
        service_type: ClusterIP
    ```

    ```bash
    helm upgrade --install belfry-operator {{ release.helm_repo_name }}/{{ release.helm_chart }} \
      --namespace awx --create-namespace --version {{ release.chart_version }} -f values.yaml
    ```

    Helm does not update CRDs on `helm upgrade`. See [Upgrading Belfry](upgrade.md#helm).

The operator image of a release deploys the Belfry images of the same release by default (`ghcr.io/belfry-project/belfry:{{ release.version }}` and `ghcr.io/belfry-project/belfry-ee:{{ release.version }}`).

## 2. Create the `AWX` resource

The minimal resource is the same as for AWX. Without any image fields, the operator deploys the Belfry version it was released with:

```yaml title="awx.yaml"
apiVersion: awx.ansible.com/v1beta1
kind: AWX
metadata:
  name: awx
  namespace: awx
spec:
  service_type: ClusterIP
```

```bash
kubectl apply -f awx.yaml
```

The operator now creates the PostgreSQL statefulset, runs the database migrations in a Job, and starts the `awx-web` and `awx-task` deployments. This takes a few minutes. Follow it with:

```bash
kubectl -n awx get awx,pods,jobs
kubectl -n awx logs -f deployment/awx-operator-controller-manager -c awx-manager
```

Belfry is ready when both deployments are rolled out:

```bash
kubectl -n awx rollout status deployment/awx-web --timeout=20m
kubectl -n awx rollout status deployment/awx-task --timeout=20m
```

The resource is still named `AWX`, and the objects are still called `awx-...`, so that existing installations keep working. See the [operator reference](https://belfry-project.github.io/docs/operator/) for every field of the resource: resources, node placement, external databases, LDAP, extra settings, and more.

## 3. Log in

The operator generates a password for the `admin` user and stores it in the secret `<name>-admin-password`:

```bash
kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 --decode; echo
```

To choose the password yourself, create the secret **before** the `AWX` resource and name it in `admin_password_secret`:

```bash
kubectl -n awx create secret generic awx-admin-password --from-literal=password='choose-a-strong-password'
```

```yaml
spec:
  admin_user: admin
  admin_password_secret: awx-admin-password
```

## 4. Expose the service

The operator creates the service `<name>-service` on port 80. Choose how to reach it:

=== "Port-forward (testing)"

    ```bash
    kubectl -n awx port-forward svc/awx-service 8080:80
    ```

    Then open <http://localhost:8080>.

=== "Ingress"

    ```yaml
    spec:
      service_type: ClusterIP
      ingress_type: ingress
      ingress_class_name: nginx
      ingress_hosts:
        - hostname: belfry.example.com
          tls_secret: belfry-tls
    ```

    The TLS secret is a normal `kubernetes.io/tls` secret in the same namespace, for example from cert-manager (add its annotation with `ingress_annotations`).

=== "OpenShift route"

    ```yaml
    spec:
      service_type: ClusterIP
      ingress_type: route
      route_host: belfry.apps.example.com
    ```

=== "NodePort / LoadBalancer"

    ```yaml
    spec:
      service_type: NodePort
      nodeport_port: 30080
    ```

    or `service_type: LoadBalancer` with `loadbalancer_port: 80`.

See [network and TLS configuration](https://belfry-project.github.io/docs/operator/user-guide/network-and-tls-configuration.html) in the operator reference for all options.

## 5. Check the installation

```bash
curl -s https://belfry.example.com/api/v2/ping/ | python3 -m json.tool
```

The `version` field shows the Belfry version. In the UI, **Administration > Execution Environments** lists `AWX EE (latest)` and `AWX EE ({{ release.version }})`, both from `ghcr.io/belfry-project/belfry-ee` (see [Execution environments](execution-environments.md#what-is-in-belfry-ee)).

Next steps:

- [Back up](backup-restore.md) your new instance regularly.
- Install the `awx.awx` collection or the `awx` CLI from the [belfry releases](https://github.com/belfry-project/belfry/releases) if you manage Belfry as code.
- [Verify the images](verify-images.md) you run, if your policies require it.
