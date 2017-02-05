dumb-pypi
-------------

[![Build Status](https://travis-ci.org/chriskuehl/dumb-pypi.svg?branch=master)](https://travis-ci.org/chriskuehl/dumb-pypi)
[![Coverage Status](https://coveralls.io/repos/github/chriskuehl/dumb-pypi/badge.svg?branch=master)](https://coveralls.io/github/chriskuehl/dumb-pypi?branch=master)
[![PyPI version](https://badge.fury.io/py/dumb-pypi.svg)](https://pypi.python.org/pypi/dumb-pypi)


`dumb-pypi` is a generator of PyPI-compatible "simple" package indexes, backed
entirely by static files.

The main difference between dumb-pypi and other PyPI implementations is that
dumb-pypi has *no server component*. It is instead a script that, given a list
of Python package names, generates a bunch of static files which you can serve
from any webserver, or even directly from S3.

This has some nice benefits:

* **File serving is extremely fast.** nginx can serve your static files faster than you'd
  ever need. In practice, there are almost no limits on the number of packages
  or number of versions per package.

* **It's very simple.** There's no complicated WSGI app to deploy, no
  databases, and no caches to purge. You just need to run the script whenever
  you have new packages, and your index server is ready in seconds.

For more about why this design was chosen, see the detailed `RATIONALE.md` in
this repo.


## Things left to do

* Currently you have to point it at a directory of packages. Instead it should
  accept a list of packages so that you don't even need to have the packages
  locally (the use-case is listing an S3 bucket and piping the results in).

* Currently it copies the packages into the output. Instead it should allow you
  to specify a URL (relative or absolute) to the packages. This would let you
  serve the files from an S3 bucket or entirely different source.

* It should have a slightly nicer HTML interface for humans to search from.


## Usage
### Generating static files

...


### Recommended nginx config

...


### Using your deployed index server with pip

...


## Contributing

...
