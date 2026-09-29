"""Fetch the Olist dataset into data/raw and verify it is the genuine file set.

Order of attempts:
1. kagglehub, only if Kaggle credentials exist (KAGGLE_USERNAME/KAGGLE_KEY or ~/.kaggle/kaggle.json).
2. A public GitHub mirror, pinned to one commit so the bytes never change under us.

Every file is checked against a SHA-256 checksum and an expected row count.
If anything does not match, we stop. Raw files are never edited after download.
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import shutil
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

KAGGLE_DATASET = "olistbr/brazilian-ecommerce"
MIRROR_REPO = "ckoliveiraa/pipeline-olist"
MIRROR_COMMIT = "e13980303baabad5213d38f6adbd4830e25026dc"
MIRROR_URL = f"https://raw.githubusercontent.com/{MIRROR_REPO}/{MIRROR_COMMIT}/raw/{{name}}.gz"

# SHA-256 of the uncompressed CSVs, and data rows (excluding header) as parsed by a CSV reader.
EXPECTED = {
    "olist_orders_dataset.csv": ("8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf", 99_441),
    "olist_order_items_dataset.csv": ("0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279", 112_650),
    "olist_order_payments_dataset.csv": ("4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0", 103_886),
    "olist_customers_dataset.csv": ("983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2", 99_441),
    "olist_products_dataset.csv": ("3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc", 32_951),
    "olist_sellers_dataset.csv": ("1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e", 3_095),
    "olist_order_reviews_dataset.csv": ("012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7", 99_224),
    "product_category_name_translation.csv": ("a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278", 71),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_complete(raw_dir: Path) -> bool:
    return all((raw_dir / name).exists() and sha256(raw_dir / name) == digest
               for name, (digest, _) in EXPECTED.items())


def _has_kaggle_credentials() -> bool:
    return bool(os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")) or \
        (Path.home() / ".kaggle" / "kaggle.json").exists()


def _from_kaggle(raw_dir: Path) -> None:
    import kagglehub  # imported lazily: only needed on this path

    src = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    for name in EXPECTED:
        shutil.copyfile(src / name, raw_dir / name)


def _from_mirror(raw_dir: Path) -> None:
    for name in EXPECTED:
        url = MIRROR_URL.format(name=name)
        log.info("downloading %s", url)
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = gzip.decompress(resp.read())
        (raw_dir / name).write_bytes(data)


def verify(raw_dir: Path) -> dict[str, str]:
    """Raise if any file is missing or differs from the genuine dataset. Returns name -> checksum."""
    import duckdb

    sums = {}
    for name, (digest, rows) in EXPECTED.items():
        path = raw_dir / name
        if not path.exists():
            raise FileNotFoundError(f"{path} missing")
        got = sha256(path)
        if got != digest:
            raise ValueError(f"{name}: checksum {got} != expected {digest}")
        n = duckdb.sql(f"select count(*) from read_csv('{path.as_posix()}', header=true)").fetchone()[0]
        if n != rows:
            raise ValueError(f"{name}: {n} rows, expected {rows}")
        sums[name] = got
    return sums


def ensure_raw_data(raw_dir: Path) -> dict[str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    if not is_complete(raw_dir):
        attempts = ([("kaggle", _from_kaggle)] if _has_kaggle_credentials() else []) + [("github mirror", _from_mirror)]
        errors = []
        for label, fetch in attempts:
            try:
                fetch(raw_dir)
                if is_complete(raw_dir):
                    log.info("raw data fetched from %s", label)
                    break
                errors.append(f"{label}: checksums did not match")
            except Exception as exc:  # network, auth, missing file
                errors.append(f"{label}: {exc}")
        else:
            raise RuntimeError("Could not fetch the Olist dataset. " + "; ".join(errors) +
                               ". See data/SOURCE.md for manual download steps.")
    return verify(raw_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for k, v in ensure_raw_data(Path(__file__).resolve().parents[1] / "data" / "raw").items():
        print(f"{v}  {k}")
