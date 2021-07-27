# Administrators manual
This is the nextcloud charm administrators manual.

## Install
Installing the Dwellir distribution of Nextcloud 
is a simple, fully automated process and takes about 20 minutes 
in a supported cloud.

### Overview
The nextcloud installation consists of:

#### 1. Selecting a supported cloud:
The charm supports the following clouds:

**Private clouds**:

  * MAAS cloud
  * OpenStack cloud
  * LXD cloud
  * vsphere
  * Kubernetes (coming soon)

**Public clouds:**

* Amazon Web Services (AWS) 
* Google Cloud Engine (GCE)
* Kubernetes (coming soon)

#### 2. Select & configure supported primary storage backend
  * CEPH (rados-gw)
  * NFS
    
#### 3. Selecting a redis backend
  * Redis Singleton 
  * Redis cluster

#### 4. Setting pre-deployment charm config
* Set an initial admin password.
* Set a domain name for your site.

This goes into a "bundle.yaml" which will be deployed into your IaaS cloud.

### Deploy your Nextcloud

    juju deploy dwellir-nextcloud-bundle.yaml

## Charm Configuration 
Configuring the nextcloud charm is done through Juju. 
All aspects of configuring Nextcloud itself is covered 
by the Nextcloud manual.

### Overview

    juju config nextcloud .... 

## Upgrading
Upgrading in a Dwellir Nextcloud deployment can be divided in four categories:  

### Juju infrastructure upgrade
Juju is upgraded normally by controller or model upgrades.

Follow the upgrade process of Juju for controller and model upgrade.


    juju upgrade controller

    juju upgrade model

Dwellir Nextcloud charm is compatible with juju 2.8 and later.

### Charm upgrade
Upgrading the juju charm:
    juju upgrade-charm nextcloud

This will get the latest stable nextcloud charm from charmhub.io and will 
not disturb or alter a running operation. 

### Nextcloud upgrade
Upgrading nextcloud to a new release is done by:
    juju config nextcloud-source="http://nextcloud.tar.gz"
    juju run-action nextcloud/0 upgrade --wait

### Series (operating system) upgrade
Upgrading the operating system for Nextcloud typically will affect
all components Nextcloud depends on. Apache webserver, php etc.

A good idea is to test in a new juju model before "apt get upgrade".

## Security
The security of your Nextcloud instance involves protecting 
every level in your total infrastructure for Nextcloud. 

### Cloud level security
Maintain your private MAAS, LXD or OpenStack to fully secure your infrastructure.

Public clouds (AWS, GCE, Azure, etc.) does not (and can not) provide 
the highest level protection of your data but, its perfectly possible 
to run Nextcloud in any public cloud.

Consult your cloud technology to secure it properly.

### Juju level security
Write me

### Charm level security
The juju charm does not contain any secrets or deploy opaque code.
It implements code integrity checks as part of upgrade and installs to
secure modifications to the system. It never sends data out from the system
not part of the Juju operation itself.

### Nextcloud level security
The Dwellir deployment implements the best practice security hardening of 
Nextcloud as described in the manual.

### SSL-certs/keys/secrets
Managing SSL-certs is done through the "tls-proxy" charm and is straight forward.

## High availability
Adding units to nextcloud that is related to a haproxy seamlessly adds 
both load balancing and high availability to your running instance.

    juju add-unit nextcloud

## Backup & Restore

### Database
See postgresql charm documentation.

### Primary storage/data
See the documentation for your selected primary storage charms.

### Configuration
The nextcloud instances doesn't need backups since they will be 
identically setup as part of adding or removing units.

## Day to Day operations
### Logging, Monitoring, Alerting
    juju deploy my-lam-bundle.yaml

### Sign a support contract with Dwellir
Dwellir disitribution of Nextcloud offers a range of services:

* Deployment services of Nextcloud in your cloud.
* Day to day operations of your Nextcloud deployment.
* Fully maintained Nextcloud instances in our datacenters.
* Fully maintained Nextcloud instances in your datacenter.
* 24/7 support in all timezones.
* Compliant to all levels of GDPR.
* Not within the reach of the Cloud Act.

https://dwellir.com