# Lab Turn Completion agreement annotation

This app serves the same blinded Turn Completion batch to multiple lab annotators. Each annotator receives a private tokenized URL and has separate saved progress.

## Data contract

Download the Hugging Face dataset to a local directory containing:

```text
tasks.json
audio/<blind-case-key>.wav
```

The public dataset excludes human labels, Judge labels, model identities, and the private model-to-case mapping.

## Deploy

1. Download the dataset from Hugging Face into a directory on the server.
2. Create private annotator links:

   ```bash
   python lab_ctc_agreement_app/create_annotators.py \
     --base-url https://YOUR_HOST/annotate \
     --output /PRIVATE_PATH/annotators.json \
     Alice Bob Carol
   ```

3. Start the app:

   ```bash
   DATASET_DIR=/PATH/TO/DATASET \
   ANNOTATORS=/PRIVATE_PATH/annotators.json \
   HOST=127.0.0.1 PORT=8765 \
   bash lab_ctc_agreement_app/run.sh
   ```

4. Put an authenticated HTTPS reverse proxy in front of `127.0.0.1:8765`. Give each annotator only their own URL from `annotators.json`.

Results are saved under `lab_ctc_agreement_data/results/<token>/<case-key>.json`. Back up this directory during annotation.

## Annotation fields

- whether the first model response is Turn Completion;
- whether a Turn Completion sounds like a natural completion in real conversation;
- corrected filler end, transcripts, and an optional note.

The interface intentionally hides model identity and automatic Judge labels.
