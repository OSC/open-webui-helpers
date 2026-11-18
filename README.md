# open-webui-helpers

## Setup development environment

Check version of Python used by Open WebUI

```
make print-python-version
```

Create uv venv:

```
uv venv --python 3.12.16 --seed --allow-existing
source .venv/bin/activate
```

Install dependencies:

```
make install
```

## Release process

Pull requests will sync functions to the test Open WebUI at OSC.

Tags will sync to production.  Generate tags on the Releases page of Github.
