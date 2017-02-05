# Design rationale

This document contains various bits of information discovered while
implementing dumb-pypi, and explains why certain decisions were made.

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
bit more than the rewrite engines in Apache or nginx can accomplish, but it can
still be accomplished pretty easily.

In nginx, you could write:

```nginx
TODO: this
```


## "api-version" meta attribute

Old versions of pip (like 6.0.0) have extra restrictions when using a meta tag
like `<meta name="api-version" value="2" />`. Newer versions (at least `>= 8`,
possibly earlier) do not enforce these.

Some example restrictions:

* Links must have `rel="internal"`, even if you're using a relative URL or a
  URL to the same server, or pip refuses to download files unless you specify
  `--allow-external {packagename}`. This isn't a problem—we could do this.

* Packages must have hashes at the end of their links. This is a bigger
  problem, because it means that in order to construct the index, we need to
  have the actual files on-hand, and hash them (which is prohibitively
  expensive to do during a full rebuild with tens of thousands of packages).

  This is an admittedly "nice-to-have" feature, but it significantly increases
  complexity. Hashing is too slow to do on-demand, so we'd need to somehow
  cache those, and then figure out when to invalidate them, and it gets too
  complicated quickly.

  For internal PyPI registries, this is an unnecessary feature, since you
  should be serving both the index and the packages from a trusted source over
  HTTPS, which already ensures integrity. The only real case that the hash is
  necessary is when you trust the index server but not the file host, which is
  not a scenario most people are concerned with.

Because of the above, we do not set this meta attribute. This gains us
compatibility with older versions of pip at no cost.
