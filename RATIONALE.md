# Design rationale

[PEP 503](https://www.python.org/dev/peps/pep-0503/) is the canonical reference
for the PyPI "simple" API, but it is not complete (if you follow it fully, old
clients cannot use your PyPI server).


## Summary of PyPI client behaviors

The primary difference between different versions of pip is that newer versions
do progressively more normalizing of package names in the initial request.

PEP 503 states that clients must not rely on the PyPI server to redirect
requests from an unnormalized name to a normalized one, but unfortunately this
is not the world we live in. If you need to support older versions of pip, your
PyPI server must be able to accept requests for unnormalized package names and
redirect or serve them.


### pip >= 8.1.2

Full normalization of package names is done before making a request to PyPI.

* `pip install ocflib` => `/ocflib`
* `pip install aspy.yaml` => `/aspy-yaml`
* `pip install ASPY.YAML` => `/aspy-yaml`

(Yes, this behavior was introduced in a *patch release* to the 8.1.x series.)

Note that even with the latest pip versions, normalization is not fully applied
to non-wheel links. So you might get to the right listing, but won't find the
archive.  For example, `aspy.yaml` has these links (files) on public PyPI:

* aspy.yaml-0.2.0.tar.gz
* aspy.yaml-0.2.1.tar.gz
* aspy.yaml-0.2.2-py2.py3-none-any.whl

You can pip install `aspy.yaml==0.2.1` but not `aspy-yaml==0.2.1`, but you
*can* install `aspy-yaml==0.2.2` (wheel names are treated differently). The
same thing does *not* happen with capitalization (you can install
`ASPY.YAML==0.2.1`).


### 6 <= pip <= 8.1.1

Some normalization is done (e.g. capitalization) but not all (e.g. dots not
transformed to dashes).

* `pip install ocflib` => `/ocflib`
* `pip install aspy.yaml` => `/aspy.yaml`
* `pip install ASPY.YAML` => `/aspy.yaml`


### pip < 6, easy_install

No normalization is done.

* `pip install ocflib` => `/ocflib`
* `pip install aspy.yaml` => `/aspy.yaml`
* `pip install ASPY.YAML` => `/ASPY.YAML`


## Package name normalization

PEP 503 defines it like this:

```python
def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()
```

Unfortunately this means you'll need to regex sub incoming requests, which is a
bit more than the rewrite engines in Apache or nginx can accomplish.

This can easily be implemented in a web server like nginx, which enables you to
serve from a set of static files (i.e. no need to run a Python service).

In nginx, you would write:

```nginx
rewrite ^/simple/([^/])(.*)$ /simple/$1 redirect;
```
