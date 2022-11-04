# collabora-office

This charm was written to deploy a stand-alone Collabora Office server for Nextcloud. It is based on this [guide](https://docs.nextcloud.com/server/latest/admin_manual/office/example-ubuntu.html).  
If using this for something else, the charm might need improvements. The config parameters have been added just to make it work with Nextcloud.

Collabora Office needs its own domain address. How to configure it in the reverse proxy can be read at https://sdk.collaboraonline.com/docs/installation/Proxy_settings.html#proxy-settings  
Example haproxy configuration for Nextcloud with Collabora Office:

    frontend haproxy
      bind 0.0.0.0:443 ssl crt /var/lib/haproxy/certs/ no-sslv3
      acl url_discovery path /.well-known/caldav /.well-known/carddav
      acl collabora req.hdr(Host) -i -m dom office.dwellir.com
      http-request redirect location /remote.php/dav/ code 301 if url_discovery
      use_backend office_dwellir_com if collabora
      default_backend nextcloud_dwellir_com

    backend office_dwellir_com
      mode http
      hash-type consistent
      balance url_param WOPISrc
      timeout tunnel 3600s
      server office_dwellir_com 192.168.111.162:9980

    backend nextcloud_dwellir_com
      mode http
      balance leastconn
      option forwardfor header X-Real-IP
      server nextcloud_dwellir_com 192.168.111.142:80 maxconn 30
      http-response set-header X-Frame-Options SAMEORIGIN
      http-response set-header X-Content-Type-Options nosniff
      http-response set-header Strict-Transport-Security max-age=16000000;\ includeSubDomains;\ preload;

The Collabora Office URL needs to be set in Nextcloud at `Settings -> Administration -> Office -> User your own server`.

## Other resources
- [Read more](https://www.collaboraoffice.com/)
