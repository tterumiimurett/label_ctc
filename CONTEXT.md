# Turn Completion Annotation

This context defines the judgments used to train and qualify annotators who review candidate turn completions in conversational audio.

## Language

**Turn completion (CTC)**:
An interruption in which the second speaker supplies material that helps complete the first speaker's unfinished utterance.
_Avoid_: Relevant overlap, generic interruption

**CTC decision**:
The binary `relevant_interruption` judgment stating whether a candidate is a turn completion.
_Avoid_: Candidate validity

**Speaker stuck**:
A separate judgment stating whether the interrupted speaker is having trouble completing the utterance. A CTC can occur without the speaker being stuck.
_Avoid_: CTC validity

**Word or phrase fit**:
The `word_phrase_fits` judgment stating whether the supplied word or phrase fits the interrupted speaker's intended meaning. It does not mean the interrupted speaker explicitly accepted it afterward.
_Avoid_: Speaker agreement, uptake

**Expert anchor**:
A candidate whose applicable field has the same label from Terumi, Shutong, and Zhifeng. Agreement on one field does not create a gold label for another field.
_Avoid_: Majority label

**Scorable field**:
A field with a unanimous three-expert label that may be used to assess a qualification response. Unscored fields remain available for diagnostic review.
_Avoid_: Inferred gold

**Teaching set**:
A disclosed set of examples used to explain annotation boundaries, including answers and discussion. Its candidates must not appear in the blind qualification set.
_Avoid_: Training test

**Qualification set**:
A blind, disjoint set used to decide whether an annotator may enter formal annotation.
_Avoid_: Teaching set, calibration examples

**Confusing item**:
A candidate that remains scorable for the unanimous CTC decision but has disagreement on at least one secondary field. A mistake on one confusing item is not by itself a disqualification.
_Avoid_: Incorrect item
