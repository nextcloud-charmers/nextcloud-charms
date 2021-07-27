## Create a cert with letsencrypt.

    sudo certbot certonly --standalone -d qcloud.dwellir.com --non-interactive --agree-tos --email info@dwellir.com

## Deploy the haproxy

    juju deploy haproxy

## Get the certs and base64 encode them as config.

    juju config haproxy ssl_cert="$(base64 fullchain.pem)"
    juju config haproxy ssl_key="$(base64 privkey.pem)"

## Create config + services options.

Easiest is to create a config file.
```
cat qcloud.yaml 
- service_name: qcloud
  service_host: "0.0.0.0"
  service_port: 443
  crts: [DEFAULT]
  service_options:
      - balance leastconn
      - reqadd X-Forwarded-Proto:\ https
  server_options: maxconn 100 cookie S{i} check
```

    juju config haproxy services="$(cat qcloud.yaml)"
