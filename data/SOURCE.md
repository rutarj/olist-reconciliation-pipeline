# Data source and provenance

## Dataset

**Brazilian E-Commerce Public Dataset by Olist**
Canonical page: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce (owner: `olistbr`)

## License and attribution

- License: **CC BY-NC-SA 4.0** (Attribution-NonCommercial-ShareAlike 4.0 International), as listed on the Kaggle dataset page. https://creativecommons.org/licenses/by-nc-sa/4.0/
- Attribution: the dataset was "generously provided by Olist, the largest department store in Brazilian marketplaces." It holds about 100k orders placed from 2016 to 2018 at multiple marketplaces in Brazil. The data is real, anonymised commercial data; references to companies and partners in the review text were replaced with the names of Game of Thrones great houses.
- What this means for this repo: non-commercial use only, credit Olist, and anything derived from the data (processed tables, the small test fixtures) is shared under the same license.

> Verification note: the Kaggle site (`www.kaggle.com`) was blocked by the network policy of the machine that built this project, so the license and attribution above were taken from the Kaggle page's indexed text in a web search on 2026-09-29, not read directly on the page. Open the Kaggle page once and confirm the license badge still says CC BY-NC-SA 4.0.

## Where the files actually came from

| Attempt | Result |
|---|---|
| 1. Kaggle (`kagglehub` / Kaggle API) | Blocked: no Kaggle credentials in the environment, and `www.kaggle.com` returned HTTP 403 from the egress proxy. |
| 2. Hugging Face mirror `aviahYadler/Olist_Ecommerce_Dataset` | Blocked: `huggingface.co` returned HTTP 403 from the egress proxy. Kept here as a fallback for other machines. |
| 3. GitHub mirror `ckoliveiraa/pipeline-olist`, folder `raw/` (gzipped CSVs) | **Used.** Pinned to commit `e13980303baabad5213d38f6adbd4830e25026dc`. |

Download URL pattern:
`https://raw.githubusercontent.com/ckoliveiraa/pipeline-olist/e13980303baabad5213d38f6adbd4830e25026dc/raw/<file>.csv.gz`

- Download date: 2026-09-29
- Downloaded by: `src/download.py` (runs automatically from `python run_pipeline.py` when `data/raw/` is empty)

### How the mirror was checked

1. Row counts match the known sizes of the genuine dataset: orders 99,441, order items 112,650, payments 103,886.
2. Two independent GitHub mirrors were compared byte for byte:
   - `wheff70/OlistDataAnalysis` (commit `4dd988203a451a2b790572937d94f15c5ac27f29`): identical SHA-256 for orders, order items, payments, customers, products and the category translation file.
   - `lavanyabk/Predictive-Analysis-on-Olist-dataset`: identical for orders, payments, customers, products and sellers. **Rejected as a source** because its order items file is missing the `shipping_limit_date` column and its reviews file has 100,000 rows instead of 99,224, so it was edited or comes from an older release.
3. The reviews file has 99,224 records (104,719 physical lines because review comments contain line breaks), which matches the current Kaggle release.

## Checksums (SHA-256 of the uncompressed CSV files in `data/raw/`)

| File | Rows | SHA-256 |
|---|---:|---|
| olist_orders_dataset.csv | 99,441 | `8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf` |
| olist_order_items_dataset.csv | 112,650 | `0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279` |
| olist_order_payments_dataset.csv | 103,886 | `4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0` |
| olist_customers_dataset.csv | 99,441 | `983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2` |
| olist_products_dataset.csv | 32,951 | `3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc` |
| olist_sellers_dataset.csv | 3,095 | `1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e` |
| olist_order_reviews_dataset.csv | 99,224 | `012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7` |
| product_category_name_translation.csv | 71 | `a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278` |

`src/download.py` holds the same checksums and refuses to run the pipeline if any file differs.

## Rules

- `data/raw/` is read only. Nothing in this project writes to it except the downloader, and only when files are missing.
- `data/raw/` is git-ignored. Run `python run_pipeline.py` to fetch it.

## Manual fallback

If the automatic download fails on your machine:
1. Log in at https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and click **Download**.
2. Unzip the 9 CSVs into `data/raw/` (the geolocation file is not used and can be skipped).
3. Run `python -m src.download` to confirm the checksums match.
