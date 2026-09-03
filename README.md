# open-webui-helpers

## Setup development environment

Check version of Python used by Open WebUI

```
make print-python-version
```

Create uv venv:

```
uv venv --python 3.11.16 --seed --allow-existing
source .venv/bin/activate
```

Install dependencies:

```
make install
```
