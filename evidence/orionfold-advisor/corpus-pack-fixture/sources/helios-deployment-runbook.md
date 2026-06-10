# Helios Deployment Runbook

Synthetic fixture document (fictional customer) for the Orionfold Advisor
corpus-pack swap gate.

## Topology

A standard Helios deployment is three services on one on-site server: the
intake collector on port 7410, the modeling worker, and the advisor API on
port 7420. All services run as containers under a single compose file named
`helios-stack.yaml`.

## Installation steps

1. Provision a server with 64 GB RAM and 2 TB NVMe storage.
2. Load the container bundle with `helios bundle load helios-2.4.1.tar`.
3. Initialize the site database with `helios db init --site-id <SITE>`.
4. Register each battery string with `helios string add`.
5. Start the stack with `helios up` and confirm health at `/api/health`.

## Upgrade policy

Upgrades are quarterly. The modeling worker must drain its queue before an
upgrade; the runbook step is `helios worker drain --wait`. Rollback is one
command, `helios rollback`, and restores the previous bundle within 5 minutes.
