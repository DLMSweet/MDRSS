# Summary

This is a rather terrible RSS feed generator for Mangadex.

It uses a flask service, Nginx, and redis for caching. 

Because MD has rather strict API limits, the caching helps prevent you from getting temporarily banned.

This has only been tested on Ubuntu 20.04, but in theory anything with Python 3.8 or newer should work. It's also worth noting that it's been a minute (read: a while) since I last set this up. This shuld be all that's required, from what I recall. 


## Pre-Reqs

Install python3, nginx, and redis.

```
apt install python3 python3-venv nginx redis redis-server
```

Clone the repo to a folder of your choosing. 

```
cd /opt/
git clone https://github.com/DLMSweet/MDRSS.git
```

Setup a python virtual environment and install python packages

```
cd MDRSS
python -m venv venv
pip install -r requirements.txt
```

## Start up the Flask service

Copy the example systemd script:
```
sudo cp example/systemd/md_rss.service /etc/systemd/system/
```

You may need to edit the following lines in `/etc/systemd/system/md_rss.service` to match the directory you're installing this into:

```
WorkingDirectory=/opt/MDRSS
ExecStart=/opt/MDRSS/venv/bin/hypercorn md_rss:app -w 16 --access-logfile -
```

At this point you should be able to start the Flask portion of this by running:

```
sudo systemctl daemon-reload
sudo systemctl start md_rss.service
```

## Configure Nginx

To configure nginx, copy the example configuration to `/etc/nginx/sites-available/` and edit a few things.
```
sudo cp example/nginx/example.conf /etc/nginx/sites-available/mdrss.conf
```

Inside that, you'll need to edit any line with 'CHANGEME' in it:
```
        server_name CHANGEME;
        ssl_certificate     /etc/letsencrypt/live/CHANGEME/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/CHANGEME/privkey.pem;
        root /var/www/CHANGEME/html;
        access_log /var/log/nginx/CHANGEME_access.log;
        server_name CHANGEME;
```

If you aren't going to set up SSL, you can skip this and replace the entire config with:
```
upstream app_server {
    # fail_timeout=0 means we always retry an upstream even if it failed
    # to return a good HTTP response
    server 127.0.0.1:8000 fail_timeout=0;
}


server {
        listen              80 deferred;
        listen              [::]:80;

        server_name CHANGEME;

        root /var/www/CHANGEME/html;
        access_log /var/log/nginx/CHANGEME_access.log;

        index index.html ;

        server_name CHANGEME;

        location / {
                # First attempt to serve request as file, then
                # as directory, then fall back to displaying a 404.
                try_files $uri @proxy_to_app;
        }

        location @proxy_to_app {
             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
             proxy_set_header X-Forwarded-Proto $scheme;
             proxy_set_header Host $http_host;
             # we don't want nginx trying to do something clever with
             # redirects, we set the Host: header above already.
             proxy_redirect off;
             proxy_pass http://app_server;
        }


}
```
That should be typo-free, but I didn't test it. 

Once that's done, you should be able to enable the site for Nginx and reload the webserver.

```
sudo ln -s /etc/nginx/sites-available/mdrss.conf /etc/nginx/sites-enabled/mdrss.conf
sudo systemctl reload nginx
```

Annnnd that's should be it. That should have things running.

# What

This is the worst code, it's true. It's a miracle it works and it's another miracle that I'm not getting soft-banned all the time. 

# Why

Because the MD Devs, bless their souls, are too busy implementing the features everyone wants to cater to the demands of the dozen of us that want RSS feeds - and individual RSS feeds per manga no less!
I just like having my RSS feed reader be organized. 
