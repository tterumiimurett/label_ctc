# Lab Turn Completion agreement annotation

This app serves the same blinded Turn Completion batch to multiple lab annotators. Each annotator receives a private tokenized URL and has separate saved progress.

## Data contract

Download the private 160-case dataset into a persistent directory outside the
Git worktree. It contains the initial 46, follow-up 34, and final 80 cases:

```bash
hf download tterumiimurett1/ctc-turn-completion-agreement-160 \
  --repo-type dataset \
  --revision a8e746b90c4f14cd0610b43da3447b8302100e43 \
  --local-dir /PATH/TO/ctc-agreement-160

cd /PATH/TO/ctc-agreement-160
sha256sum -c SHA256SUMS
```

The downloaded directory contains:

```text
tasks.json
audio/<blind-case-key>.wav
```

The 160 cases comprise 93 with written context and 67 with spoken context.
`context_mode` distinguishes them. For written context, `context_text` gives
the original text shown to the model. For spoken context, it gives the source
text used to generate the spoken context; this is not an ASR transcript.
All WAVs begin with the user question and exclude the preceding spoken
context audio. `filler_end_s` is relative to the start of the packaged WAV.

The private Hub dataset excludes human labels, Judge labels, model identities,
original sample IDs, and the private model-to-case mapping. There are 161
checksums: `tasks.json` plus 160 WAV files. The mapping is kept in pi-bench at
`.scratch/ctc-turn-completion-agreement-160-private-case-map.json` and is not
part of the upload.

To rebuild locally from pi-bench:

```bash
python lab_ctc_agreement_app/prepare_dataset.py \
  --pi-bench /PATH/TO/pi-bench \
  --output /PRIVATE/PATH/ctc-agreement-160 \
  --private-mapping-output /PRIVATE/PATH/ctc-case-map.json
```

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
   DATASET_DIR=/PATH/TO/ctc-agreement-160 \
   ANNOTATORS=/PRIVATE_PATH/annotators.json \
   DATA_DIR=/PRIVATE_PATH/ctc-results \
   HOST=127.0.0.1 PORT=8766 \
   bash lab_ctc_agreement_app/run.sh
   ```

4. Put an authenticated HTTPS reverse proxy in front of `127.0.0.1:8766`. Give each annotator only their own URL from `annotators.json`.

Results are saved under `DATA_DIR/results/<token>/<case-key>.json`. Keep this
directory and the TC service separate from the Clarification/Backchannel
service already present on this branch. `/healthz` should report
`task_count: 160`.

## Annotation fields

- whether the first model response is Turn Completion;
- whether a Turn Completion sounds like a natural completion in real conversation;
- whether the displayed transcript materially differs from the audio;
- whether the marked candidate is the first relevant model response;
- corrected filler end, transcripts, and an optional note.

The interface intentionally hides model identity and automatic Judge labels.
