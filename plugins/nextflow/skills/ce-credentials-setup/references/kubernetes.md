<!-- Adapted for the Nextflow plugin: generic host tools and OAuth MCP. -->
# Kubernetes Compute Environment Setup

Complete procedure for setting up a Kubernetes compute environment on Nextflow Platform.

## Prerequisites

- Kubernetes cluster with admin access
- `kubectl` configured and connected (`kubectl cluster-info` succeeds)
- `ReadWriteMany` storage solution (NFS, GlusterFS, CephFS, or similar)

## 1. Create Namespace and Service Account

Apply the Seqera launcher manifest:

```bash
kubectl apply -f <manifest_url_from_latest_release>
```

This creates:
- Namespace: `tower-nf`
- Service account: `tower-launcher-sa`
- Role with permissions for pods, jobs, PVCs, configmaps, secrets
- RoleBinding linking the service account to the role

### Manual Setup (if manifest not suitable)

```bash
# Create namespace
kubectl create namespace tower-nf

# Create service account
kubectl create serviceaccount tower-launcher-sa -n tower-nf

# Create role (minimum permissions)
kubectl create role tower-launcher-role -n tower-nf \
  --verb=create,get,list,watch,delete \
  --resource=pods,jobs,configmaps,secrets,persistentvolumeclaims

# Bind role to service account
kubectl create rolebinding tower-launcher-binding -n tower-nf \
  --role=tower-launcher-role \
  --serviceaccount=tower-nf:tower-launcher-sa
```

### Required RBAC Permissions

| Resource | Verbs |
|----------|-------|
| pods | create, get, list, watch, delete |
| pods/log | get, list |
| pods/status | get |
| jobs | create, get, list, watch, delete |
| configmaps | create, get, delete |
| secrets | create, get, delete |
| persistentvolumeclaims | create, get, delete |

## 2. Get API Server URL

```bash
# From cluster-info
kubectl cluster-info | grep "Kubernetes control plane"
# Output: Kubernetes control plane is running at https://1.2.3.4:6443

# Or from kubeconfig
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

## 3. Bearer Token and SSL Certificate

The service account token and the cluster CA certificate are secrets. Do not
read, print or copy them yourself, and do not run commands whose output
contains them.

Ask the user to:

1. Create a token for the service account from the manifest (`tower-launcher-sa`
   in namespace `tower-nf` by default) in their own terminal, following the
   Kubernetes service account token documentation and their cluster
   administrator's policy on token lifetime.
2. Copy the cluster CA certificate (the base64-decoded
   `certificate-authority-data` of their cluster entry, or the certificate file
   their Kubernetes configuration refers to).
3. Paste both directly into the Seqera Platform credentials form
   (**Credentials > Add credentials > Kubernetes**) and tell you the
   credential name.

Verify the service account's required permissions against the user-selected
cluster using its trusted certificate and current Kubernetes authentication.
Do not disable certificate verification to bypass a failure.

## 4. Set Up Persistent Storage

Nextflow requires a `ReadWriteMany` PVC for shared work directories.

### NFS Example

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: tower-scratch
  namespace: tower-nf
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 100Gi
  storageClassName: nfs-client  # Adjust to your storage class
```

Apply the user's reviewed persistent-volume-claim definition using the available
Kubernetes tools and verify that the selected claim is bound.

### Verify Storage

```bash
# Check PVC is bound
kubectl get pvc -n tower-nf
# NAME             STATUS   VOLUME   CAPACITY   ACCESS MODES
# tower-scratch    Bound    pv-xxx   100Gi      RWX

```

Validate read and write access using an administrator-approved temporary pod,
the user's actual persistent volume claim, and the mount configuration chosen
for the compute environment. Remove only the temporary test artifacts created
for this check.

## 5. Find the Credentials in Seqera

The user created the Kubernetes credentials in step 3. Discover the
credential-listing operation with `search_seqera_api`, call
`platform_list_credentials` through `call_seqera_api`, and take the ID of the
credential the user named. Do not create Kubernetes credentials with the token
or certificate yourself.

## 6. Create Compute Environment in Seqera

```
platform_create_compute_env(
    workspace_id=<ws_id>,
    name="k8s-<cluster-name>",
    platform="k8s",
    credentials_id="<cred_id>",
    config={
        "server": "<api_server_url_from_step_2>",
        "namespace": "tower-nf",
        "headServiceAccount": "tower-launcher-sa",
        "storageClaimName": "tower-scratch",
        "storageMountPath": "<user-provided mount location>",
        "workDir": "<user-provided work location>"
    }
)
```

## Troubleshooting

### Token not working

```bash
# Check token is valid
kubectl --token="<token>" get pods -n tower-nf 2>&1

# Check service account exists
kubectl get sa tower-launcher-sa -n tower-nf

# Check role binding
kubectl get rolebinding -n tower-nf
```

### SSL certificate issues

Inspect the certificate supplied by the user for issuer, subject, and validity.
Confirm it matches the selected cluster, and verify the API server's health
endpoint using the trusted certificate. Do not prescribe a certificate location.

### Storage issues

```bash
# Check PVC status
kubectl describe pvc tower-scratch -n tower-nf

# Check storage class exists
kubectl get sc

# Check PV is available
kubectl get pv
```

### Network issues

```bash
# Test API server reachability from within cluster
kubectl run test-net --rm -i --tty -n tower-nf --image=curlimages/curl \
  -- curl -k <api_server_url>/healthz

# Check firewall rules (cloud-specific)
# GKE: gcloud compute firewall-rules list
# EKS: aws ec2 describe-security-groups
# AKS: az network nsg list
```
