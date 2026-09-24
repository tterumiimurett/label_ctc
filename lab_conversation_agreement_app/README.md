# Lab Clarification / Backchannel agreement annotation

This app serves one blinded 200-case batch: 100 Clarification cases and 100 Backchannel candidate events. It covers Doubao, GPT Realtime, Freeze-Omni, and both SALMONN-Omni checkpoint variants.

Generate the private dataset:

```bash
python lab_conversation_agreement_app/prepare_dataset.py \
  --pi-bench /PATH/TO/pi-bench \
  --closed-backchannel-asr /PRIVATE/PATH/closed-backchannel-asr-v1/aligned-candidates.jsonl \
  --output /PRIVATE/PATH/conversation-agreement-200
```

The closed-model Backchannel candidates must come from GPT-4o Transcribe output
with forced alignment. Silent outputs are excluded before this build step.

Create annotator links and start the server:

```bash
python lab_conversation_agreement_app/create_annotators.py --base-url https://YOUR_HOST/annotate --output /PRIVATE/PATH/annotators.json Alice Bob Carol
DATASET_DIR=/PRIVATE/PATH/conversation-agreement-200 ANNOTATORS=/PRIVATE/PATH/annotators.json DATA_DIR=/PRIVATE/PATH/results HOST=127.0.0.1 PORT=8765 bash lab_conversation_agreement_app/run.sh
```

The browser hides model identity, prompt variant, checkpoint, and Judge labels. Labels are saved separately for each annotator.
