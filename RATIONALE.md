# Design rationale

[PEP 503](https://www.python.org/dev/peps/pep-0503/) is the canonical reference
for the PyPI "simple" API, but it is not complete (if you follow it fully, old
clients cannot use your PyPI server).


## Summary of PyPI client behaviors

The primary difference between different versions of pip is that newer versions
do progressively more normalizing of package names in the initial request.

PEP 503 states that clients must not rely on the redirection, but unfortunately
this is not the world we live in. If you need to support older versions of pip,
your PyPI server must be able to accept requests for unnormalized package names
and redirect or serve them.


### pip >= 8.1.2

Full normalization of package names is done before making a request to PyPI.

* `pip install ocflib` => `/ocflib`
* `pip install ocflib==1` => `/ocflib`
* `pip install aspy.yaml` => `/aspy-yaml`
* `pip install ASPY.YAML` => `/aspy-yaml`

(Yes, this behavior was introduced in a *patch release* to the 8.1.x series.)


### 6 <= pip <= 8.1.1

Some normalization is done (e.g. capitalization) but not all (e.g. dots not
transformed to dashes).

* `pip install ocflib` => `/ocflib`
* `pip install ocflib==1` => `/ocflib`
* `pip install aspy.yaml` => `/aspy.yaml`
* `pip install ASPY.YAML` => `/aspy.yaml`


### pip < 6, easy_install

No normalization is done.

* `pip install ocflib` => `/ocflib`
* `pip install ocflib==1` => `/ocflib`
* `pip install aspy.yaml` => `/aspy.yaml`
* `pip install ASPY.YAML` => `/ASPY.YAML`


## Package name normalization

PEP 503 defines it like this:

```python
import re

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()
```

This can easily be implemented in a web server like nginx, which enables you to
serve from a set of static files (i.e. no need to run a Python service).
