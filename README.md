dumb-pypi
---------

[![Build Status](https://travis-ci.org/chriskuehl/dumb-pypi.svg?branch=master)](https://travis-ci.org/chriskuehl/dumb-pypi)
[![Coverage Status](https://coveralls.io/repos/github/chriskuehl/dumb-pypi/badge.svg?branch=master)](https://coveralls.io/github/chriskuehl/dumb-pypi?branch=master)
[![PyPI version](https://badge.fury.io/py/dumb-pypi.svg)](https://pypi.python.org/pypi/dumb-pypi)


`dumb-pypi` is a simple read-only PyPI index server generator, backed entirely
by static files. It is ideal for internal use by organizations that have a
bunch of their own packages which they'd like to make available.

You can view [an example generated repo](https://chriskuehl.github.io/dumb-pypi/test-repo/).


## A rant about static files (and why you should use dumb-pypi)

The main difference between dumb-pypi and other PyPI implementations is that
dumb-pypi has *no server component*. It's just a script that, given a list of
Python package names, generates a bunch of static files which you can serve
from any webserver, or even directly from S3.

There's something magical about being able to serve a package repository
entirely from a tree of static files. It's incredibly easy to make it fast and
highly-available when you don't need to worry about running a bunch of
application servers (which are serving a bunch of read-only queries that could
have just been pre-generated).

Linux distributions have been doing this right for decades. Debian has a system
of hundreds of mirrors, and the entire thing is powered entirely by some fancy
`rsync` commands.

For the maintainer of a PyPI repositry, `dumb-pypi` has some nice properties:

* **File serving is extremely fast.** nginx can serve your static files faster
  than you'd ever need. In practice, there are almost no limits on the number
  of packages or number of versions per package.

* **It's very simple.** There's no complicated WSGI app to deploy, no
  databases, and no caches. You just need to run the script whenever you have
  new packages, and your index server is ready in seconds.

For more about why this design was chosen, see the detailed
[`RATIONALE.md`][rationale] in this repo.


## Usage

To use dumb-pypi, you need two things:

* A script which generates the index. (That's this project!)

* A generic webserver to serve the generated index.

  This part is up to you. For example, you might sync the built index into an
  S3 bucket, and serve it directly from S3. You might run nginx from the built
  index locally.

My recommended high-availability (but still quite simple) deployment is:

* Store all of the packages in S3.

* Have a cronjob (or equivalent) which rebuilds the index based on the packages
  in S3. This is incredibly fast—it would not be unreasonable to do it every
  sixty seconds. After building the index, sync it into a separate S3 bucket.

* Have a webserver (or set of webservers behind a load balancer) running nginx
  (with the config provided below), with the source being that second S3
  bucket.


### Generating static files

First, install `dumb-pypi` somewhere (e.g. into a virtualenv).

By design, dumb-pypi does *not* require you to have the packages available when
building the index. You only need a list of filenames, one per line. For
example:

```
dumb-init-1.1.2.tar.gz
dumb_init-1.2.0-py2.py3-none-manylinux1_x86_64.whl
ocflib-2016.10.31.0.40-py2.py3-none-any.whl
pre_commit-0.9.2.tar.gz
```

You should also know a URL to access these packages (if you serve them from the
same host as the index, it can be a relative URL). For example, it might be
`https://my-pypi-packages.s3.amazonaws.com/` or `../../pool/`.

You can then invoke the script:

```bash
$ dumb-pypi \
    --package-list my-packages \
    --packages-url https://my-pypi-packages.s3.amazonaws.com/ \
    --output-dir my-built-index
```

The built index will be in `my-built-index`. It's now up to you to figure out
how to serve that with a webserver (nginx is a good option — details below!).


#### Additional options for packages

You can extend the capabilities of your registry using the extended JSON input
syntax when providing your package list to dumb-pypi. Instead of using the
format listed above of one filename per line, format your file with one JSON
object per line, like this:

```json
{"filename": "dumb-init-1.1.2.tar.gz", "hash": "md5=<hash>", "requires_python": ">=3.6", "uploaded_by": "ckuehl", "upload_timestamp": 1512539924}
```

The `filename` key is required. All other keys are optional and will be used to
provide additional information in your generated repository. This extended
information can be useful to determine, for example, who uploaded a package.
(Most of this information is useful in the web UI by humans, not by pip.)

Where should you get information about the hash, uploader, etc? That's up to
you—dumb-pypi isn't in the business of storing or calculating this data. If
you're using S3, one easy option is to store it at upload time as [S3
metadata][s3-metadata].


### Recommended nginx config

You can serve the packages from any static webserver (including directly from
S3), but for compatibility with old versions of pip, it's necessary to do a
tiny bit of URL rewriting (see [`RATIONALE.md`][rationale] for full details
about the behavior of various pip versions).

In particular, if you want to support old pip versions, you need to apply this
logic to package names (taken from [PEP 503][pep503]):

```python
def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()
```

Here is an example nginx config which supports all versions of pip and
easy_install:

```nginx
server {
    location / {
        root /path/to/index;
        set_by_lua $canonical_uri "return string.gsub(string.lower(ngx.var.uri), '[-_.]+', '-')";
        try_files $uri $uri/index.html $canonical_uri $canonical_uri/index.html =404;
    }
}

```

If you don't care about easy_install or versions of pip prior to 8.1.2, you can
omit the `canonical_uri` hack.


### Using your deployed index server with pip

When running pip, pass `-i https://my-pypi-server/simple` or set the
environment variable `PIP_INDEX_URL=https://my-pypi-server/simple`.


## Contributing

Thanks for contributing! To get started, run `make venv` and then `.
venv/bin/activate` to source the virtualenv. You should now have a `dumb-pypi`
command on your path using your checked-out version of the code.

To run the tests, call `make test`. To run an individual test, you can do
`py.test -k name_of_test tests` (with the virtualenv activated).


[rationale]: https://github.com/chriskuehl/dumb-pypi/blob/master/RATIONALE.md
[pep503]: https://www.python.org/dev/peps/pep-0503/#normalized-names
[s3-metadata]: https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html#UserMetadata
