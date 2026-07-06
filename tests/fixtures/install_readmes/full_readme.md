# Hermia

Some intro.

## Install

Recommended (via pipx):

```bash
pipx install hermia
```

Or via Homebrew (macOS):

```bash
brew install scottblydotcom/tap/hermia
```

Or with pip:

```bash
pip install hermia
```

Or from source:

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e .
```

Or via Docker (headless fleet mode):

```bash
mkdir -p results && chmod 777 results
docker run --rm --network host \
  -v $PWD/fleets:/workspace/fleets:ro \
  -v $PWD/results:/workspace/results \
  ghcr.io/scottblydotcom/hermia:latest \
  --fleet fleets/local.yaml
```

## Quickstart

Something else.
