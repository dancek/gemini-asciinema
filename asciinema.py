# Copyright 2020 Hannu Hartikainen
# Licensed under GNU AGPL, v3 or later

import json
import gzip
from time import time, sleep
from urllib.request import urlopen

from jetforce import GeminiServer, JetforceApplication, Response, Status

app = JetforceApplication()

FRONT_CONTENT = """# Asciinema Gemini mirror
=> https://asciinema.org/ Asciinema over HTTPS

## Usage

Use a streaming-capable in an ANSI capable terminal to watch asciinema recordings over Gemini. Playback URLs are /<id>. For example:

gemget -o- gemini://asciinema.hrtk.in/22767

Note that some recordings only show correctly if you have the exact same terminal size that was used when recording. To get original size and other info, fetch /meta/<id>.

To record and publish recordings, use the official asciinema CLI.

## About this site

=> source/ Source code (AGPLv3)
=> gemini://hannuhartikainen.fi/ Copyright 2020 by Hannu Hartikainen
"""

# don't try over 10fps (that's a lot of TLS traffic...)
TARGET_FRAME_TIME = 1/10

@app.route("")
def root(req):
    return Response(Status.SUCCESS, "text/gemini", FRONT_CONTENT)

def fetch(id):
    # NOTE: this should be streaming, but it's a pain in python :shrug:
    with urlopen(f"https://asciinema.org/a/{id}.cast") as url:
        data = url.read()
        try:
            # support but don't require gzip
            data = gzip.decompress(data)
        except:
            pass
        data = data.decode()
        try:
            # version 1
            meta = json.loads(data)
            stdout = meta.pop('stdout')
            return meta, stdout
        except:
            # version 2
            meta, *lines = data.splitlines()
            meta = json.loads(meta)
            def get_stdout():
                last_ts = 0
                for line in lines:
                    ts, dir, out = json.loads(line)
                    if dir == 'o':
                        yield ts - last_ts, out
                        last_ts = ts
            return meta, list(get_stdout())

def sleep_until(ts):
    sleep(max(ts - time(), 0))

def render(stdout):
    # skip initial delay
    (_delay, output), *stdout = stdout
    yield output

    ts = time()
    buf = ""
    while len(stdout) > 0:
        next_ts_limit = max(ts+TARGET_FRAME_TIME, time())
        buf = ""
        while ts < next_ts_limit and len(stdout) > 0:
            (delay, output), *stdout = stdout
            ts += delay
            buf += output

        sleep_until(ts)
        yield buf


@app.route("/(?P<id>\d+)")
def play(req, id):
    _, stdout = fetch(id)
    if stdout:
        return Response(Status.SUCCESS, "text/x-ansi", render(stdout))
    return Response(Status.NOT_FOUND, "Not found")

@app.route("/meta/(?P<id>\d+)")
def meta(req, id):
    meta, _ = fetch(id)
    if meta:
        pretty = json.dumps(meta, indent=2)
        return Response(Status.SUCCESS, "application/json", meta)
    return Response(Status.NOT_FOUND, "Not found")


@app.route("/source")
def source(req):
    with open(__file__) as source_file:
        return Response(Status.SUCCESS, "text/x-python", source_file.read())

@app.route("/robots.txt")
def robots(req):
    return Response(Status.SUCCESS, "text/plain", """User-agent: *
Disallow: /
""")

if __name__ == "__main__":
    server = GeminiServer(app, port=45611)
    server.run()
