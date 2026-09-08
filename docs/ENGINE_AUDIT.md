# What is wrong with the class analysis

Written 9 September 2026, after four independent reviews of the code and a set of controlled runs.
Every item below was checked by running the real code. Nothing here is a guess. A claim that did
not survive checking is kept at the bottom, marked, so the record stays honest.

---

## 1. The measurement

Six recordings were analysed twice, on the very same file.

| | |
|---|---|
| Recordings analysed twice | 6 |
| Gave the same re-class answer both times | 1 |
| Average overlap of the problems found | 29% |
| Average overlap of problem and severity together | 14% |

Then one class was run three more times, same engine, same transcript, nothing else changed.

| Run | Answer | Errors found |
|---|---|---|
| this afternoon | yes, re-teach it | 2 correctness majors |
| tonight, run 1 | maybe | 1 correctness major |
| tonight, run 2 | no | none |
| tonight, run 3 | no | none |

The part of the prompt that finds problems was byte-for-byte identical across all of these. None of
the spread comes from a code change.

---

## 2. Why it happens

### R1 - The session summary only covers the first two-thirds of the class

Measured on the real Fine-Tuning recording: the class runs 1 hour 59 minutes, the summary is built
from the first 1 hour 19 minutes. It is then handed to every later pass under the heading
"WHOLE-SESSION MAP ... do not flag anything resolved elsewhere", with no note that it is partial.

Two of the three teaching errors on that recording sit past the horizon:

| Error | Time | Was it in the summary? |
|---|---|---|
| learning-rate warm-up | 00:50:27 | yes |
| top-p explained wrongly | 01:23:53 | **no** |
| goal of fine-tuning stated wrongly | 01:57:06 | **no** |

The summary is also asked to report what was "left unresolved by the END of the session".

### R2 - The summary call is given a very small output budget and is never checked

1,200 tokens, no validation, no retry, and the code never asks whether the model was cut off. If it
returns nothing, the heading is still inserted with nothing under it, and the run reports that the
session was mapped.

### R3 - The system is told four separate times to under-report, and never once to be thorough

"Prefer precision over completeness: if unsure, do NOT raise the flag." "You prefer returning
nothing." "Tie-break: use the LOWER severity." "Only include findings with evidence in THIS
segment." A factual teaching error is exactly the case where the model is least certain, so the
instruction resolves it toward silence. That is where a real error becomes a coin flip.

### R4 - Nothing can ever be added back

Six code paths lower or delete a finding. Zero can raise one. Five separate guards exist purely to
stop anything being raised. A missed error stays missed forever.

---

## 3. The defects, checked one by one

### Decisions that come out wrong

| # | What is wrong | Checked how |
|---|---|---|
| D1 | The same error can be labelled correctness or clarity. Both definitions claim factual accuracy. In a test review one forces a re-teach and the other cannot. | Seen on a real class: the same misstatement was correctness in one run, clarity in the next |
| D2 | The stage that picks the label is never told what the label does. The words re-class, re-taught and re-attend appear in no extraction prompt. No later stage may relabel. | Prompt text |
| D3 | The severity floor blocks the mild action and permits the total one. A test-review correctness finding cannot be downgraded, but it can be deleted outright. | Ran it: flag gone, re-class softened to maybe |
| D4 | The same floor never applies on the way in. The identical finding arriving as moderate simply stays moderate. | Ran it |
| D5 | A finding the model itself marked **low confidence**, which the verifier tried to reduce to minor, comes out as major and produces "yes". Confidence is collected and used nowhere. | Ran it |
| D6 | The re-class gate is one-directional. It can only soften "yes". "No" and "maybe" are never revisited, so a "maybe" needs no surviving evidence at all. | Code, single write site |
| D7 | The stricter second vote falls only on findings that could justify a re-teach, and tells the model a re-attend decision rests on them even when the call is "no". The more skeptical of the two votes always wins. | Code |
| D8 | The reason can name findings that were deleted. Deciding flags are never reconciled after verification. | Ran it: correctness dropped, still named |

### Whole classes lost or silently cut short

| # | What is wrong | Checked how |
|---|---|---|
| D9 | The test-review prompt asks for four flags the test-review validator rejects: coding_time, coverage, examples, slides_mismatch. If the model obeys, one retry is spent and then the whole class analysis dies. The extraction call has no try/except. | Ran it |
| D10 | coverage cannot legally exist in a test review, yet it is one of the four flags that decide a re-teach. Only three of the four doors are open there. | Ran it |
| D11 | One out-of-order caption line silently discards the rest of the class. A trailing "thanks for joining" stamped near zero cut a test file from 121 lines to 16. | Ran it: 105 lines never analysed |
| D12 | Valid WebVTT that omits the optional hours field crashes the whole analysis. | Ran it |
| D13 | A caption file whose blocks are not separated by a blank line collapses the entire class into one line. | Ran it |
| D14 | Ordinary words become "speakers" after two uses and are then deleted from the text. "Note:", "Output:", "Right:" were all read as people in the room. | Ran it |
| D15 | Findings are never checked when extracted. A timestamp of "banana" with an empty quote is accepted. | Ran it |
| D16 | A quote copied with its speaker name or its timestamp fails the transcript match, and the verifier is told to treat unmatched quotes as suspect. | Ran it |
| D17 | The visual track stops at 2 hours 29 minutes however long the class is, and still reports "60/60 frames". A four-hour class has its last 91 minutes unseen while the page shows a video-verified badge. | Ran it |

### Failures nobody can see

| # | What is wrong |
|---|---|
| D18 | When verification fails, the analysis is saved and shown exactly like a verified one. No badge, no error, no note. The video stage does this correctly and shows a "Transcript only" badge. |
| D19 | The verification status is never stored in the database at all. It exists in memory for the length of the job and is then thrown away. |
| D20 | In that same state the system asserts a check that never happened, stamping "no major finding survived verification" onto the reason. |
| D21 | When the prose clean-up fails, the feedback and the reason keep arguing for findings that were deleted, next to a panel listing them as removed. |
| D22 | The second vote can fail with no record anywhere. "Verification ran" is reported as true even when it was never called. |
| D23 | Nothing ever checks whether a reply was cut off mid-answer. The repair asks again with the same budget and no sight of what was cut, so a window that was producing twelve findings can come back with six and look normal. |
| D24 | A failed video stage reports its spend as zero. A class that dies partway reports no cost at all. |

### Smaller, still real

An unknown severity collapses to the least serious. A finding timestamped "MM:SS" silently gives
the verifier no transcript excerpt. A model reply that opens with a sentence before the JSON burns
the single repair attempt. The materials fetch retries three times with no pause, so a rate limit
fails all three instantly. A Spanish caption track outranks an English one. An unlisted video's
link is parsed and then dropped, so the fetch fails and the PM is told their correct link is wrong.

---

## 4. What this means for the formula test

The twelve-class run cost $5.89 and produced a clean-looking table. It cannot settle the formula
question, for two reasons.

**The answers are not repeatable.** One class run three times gave maybe, no, no, and yes earlier
the same day.

**No class agenda was supplied.** Every run passed the literal words "(not provided)", while the
rubric tells the model the agenda is in front of it and to judge coverage against it. The model
reconstructed a plan from the instructor's own opening remarks and then graded the instructor
against its own reconstruction. Coverage is one of the four flags that can force a re-teach.

The Test B side is less affected, because there the question is only whether anything serious was
found at all, and four of four came back with nothing. That half still points the same way.

---

## 5. Checked and NOT a problem

- Verdicts land on the correct findings. No off-by-one in the indexing.
- The verdict-application code itself is the strongest part of the kit: it copies before changing
  anything, clamps a downgrade to one level, records drops rather than hiding them.
- Cost arithmetic and the price constants are right, and repair calls are included.
- The materials link handling is careful, correct work.
- **Corrected:** an earlier version of this file said a quote carrying a speaker name still matched
  the transcript. That was wrong. I had passed the arguments to the checker in the wrong order. The
  reviewer was right, and it is now recorded as D16.

---

## 6. Second sweep: the parts nobody had looked at

Three more reviews covered the note the instructor receives, the machinery around the engine, and
the test suite. Everything below was proved by running code.

### The note the instructor actually receives

| # | What is wrong |
|---|---|
| D25 | A criticism whose finding was DELETED by verification can still be sent to the instructor. Proved end to end: a learner's question was mistaken for the instructor's error, verification threw it out, and the note still accused the instructor of teaching it. |
| D26 | The note is capped at five points and the code keeps the FIRST five, not the most serious. Proved: five polish notes kept, "you taught quicksort wrongly" deleted. |
| D27 | Nothing in code stops the re-teach decision leaking into the instructor's note. Four prompts forbid it; zero lines of code check. Proved to pass through unchanged. |
| D28 | Nothing checks that a timestamp in the note exists, that a quote is real, or that the note matches the surviving findings. Seven findings with prose about two, plus an accusation in no finding at all, all validate clean. |
| D29 | The note can name a learner and quote them word for word. Proved. |
| D30 | The bullet cap counts only dash bullets. Numbered lists and en-dash bullets pass straight through. |
| D31 | Trimming a wrapped bullet leaves its "Fix:" line behind, orphaned, attached to nothing. |
| D32 | The timestamp cleaner destroys ordinary sentences. "the 80:20 rule" becomes "the rule". "scheduled at 10:30" becomes "scheduled". "averaged 4:55 out of 5" becomes "averaged out of 5". |
| D33 | Every class is told "below the 4.55 line, this class was flagged", including classes rated 4.87. The number of learners who rated is never passed to the model at all. |
| D34 | The page and the approve button can be looking at two different drafts. Clearing the note and approving silently restores the original text. |
| D35 | A note that is approved but not sent is labelled "Sent". |

### The machinery around the engine

| # | What is wrong |
|---|---|
| D36 | The worker has no authentication when its key is unset, which is the shipped default. Every endpoint accepts any request. |
| D37 | If a Slack message fails to send, that class is never notified again, ever. The record is written before the send and never cleared. |
| D38 | Two analyses of the same class can run at once, both save, and the page can show one run's findings above the other run's note. |
| D39 | If the worker dies mid-job the class stays "analyzing" forever. Nothing sweeps it, the money spent is not recorded, and a class from an uploaded transcript cannot be retried at all. |
| D40 | The failure handler swallows every error silently and never closes its connection. A class deleted mid-analysis leaves no record at all. |
| D41 | The sync's own failure handling can fail. The run is left marked "running" forever and the alert is never sent. |
| D42 | The settings file reader does not strip trailing comments, so a setting written the way the example file shows it is read as the comment text. One of them silently turns the video stage off. |
| D43 | Command-line runs cache by transcript and context but not by class type, so a test review can quietly return a live-class analysis. A crash leaves an empty cache folder that reports success forever. |

### The test suite

290 tests pass in under two seconds. A reviewer fixed three of the defects above and **all 102
engine tests still passed** — the suite cannot tell the broken code from the fixed code.

Four tests pass because the code is wrong, and are named as though they cover the opposite.

Running the test file the way its own instructions say runs 56 of its 74 tests. A stray line in the
middle ends the run early, hiding all 18 tests written to check that verification is safe.

---

## 7. What has been fixed

Applied 9 September 2026. Every fix was checked by running the real code, and the checks were added
to the test suite so they cannot quietly break again. The suite went from 290 tests to 324; the 34
new ones are behavioural, because a reviewer showed that three of these defects could be fixed
without a single existing test changing status.

### Whole classes are no longer lost

| Was | Now |
|---|---|
| One out-of-order caption line discarded the rest of the class | Cues are put in order first; every cue reaches the analysis. Checked on all ten real recordings. |
| Valid WebVTT without the hours field crashed the analysis | Parsed. A genuinely malformed timestamp is still rejected loudly. |
| A file with no blank lines between blocks became one cue | Blocks are found by their timestamp line when blank lines are missing. |
| "Note:", "Output:", "Right:" became people, and the word was deleted from the transcript | A stop list of everyday teaching words. Real names still work. |
| One window whose reply would not validate killed the whole class | The window is lost, the class continues, and the loss is recorded and shown. |

### The analysis now looks at the whole class

The session summary was a prefix cut of the transcript and covered about two-thirds of a two-hour
class, while every later stage was told it described the whole session. Long classes are now
summarised in consecutive parts.

| Class | Length | Covered before | Covered now |
|---|---|---|---|
| Fine-Tuning · Suhrid | 1:59 | 65% | 100% |
| AI Product Architecture | 4:53 | about 27% | 100% |
| Leadership & People Management | 4:45 | about 28% | 100% |
| Workshop 1 · Dipti | 4:30 | about 30% | 100% |

A reply cut off mid-answer is now noticed and counted instead of passing as a short one. The video
now samples across the whole recording, and says so plainly when it could not reach the end.

### The decision is harder to get wrong

- A wrong statement is `correctness`, never `clarity`, and both rubrics say so.
- The extractor is told which labels can lead to a re-teach, so the choice is not blind.
- No prompt names a flag its class cannot return. This is now a derived test, not a wording test.
- The severity floor applies on the way in, and a floored finding can only be dropped on an
  attribution or evidence failure, not on an opinion about how serious it was.
- A finding the model itself marked low confidence can no longer ask learners to re-attend.
- The deciding flags can no longer name a finding that was deleted.
- The softening note no longer claims a verification that may not have happened.

### The model is told the truth about the class

- A class rated 4.87 is no longer described as "below the 4.55 line".
- An unknown rating makes no claim either way.
- When no agenda was supplied, the model is told so and told not to invent one and mark the
  instructor against it.

### The note the instructor receives

- Points are ordered by the severity of the finding behind them before the five-point cap, so the
  one serious point is no longer deleted to make room for five polish notes.
- Numbered and en-dash lists are counted; a trimmed point takes its own "Fix:" line with it.
- The re-teach decision is stripped out of the note in code, not just discouraged in a prompt.
- "the 80:20 rule", "scheduled at 10:30" and "averaged 4:55 out of 5" survive; real timestamps
  still go.

### Failures are visible

- Whether the self-check ran is written into the analysis itself, so it reaches the database. It
  used to live only in the worker's memory.
- The page shows "Not self-checked" with the reason, "Nothing to self-check", "Draft not tidied",
  and how many parts of the class could not be read.
- The failure handler logs instead of swallowing, closes its connection, records the cost, and no
  longer drags a class a newer run has finished back to failed.

### The worker

- With no key configured the worker used to accept every request from anyone who found its address.
  It now refuses to serve until a key is set. A local machine can opt out explicitly.
- The settings file is read the way the example file is written, so a trailing comment is no longer
  stored as the value. One of those silently switched the video stage off.
- The command-line cache includes the class kind and the model, and its folder is created only once
  there is a result to put in it.

### Closed since

- Two analyses of the same class can no longer run at once. The class is claimed before any work
  starts and a second request is refused rather than paid for.
- A Slack message that fails to send no longer buries the class. A failed record is now read as
  proof the class still needs telling somebody, and the next sync picks it up.
- The hourly sync releases any class that has been "analyzing" for more than ninety minutes and
  writes the reason to the audit log.

### Found while connecting the live sheet

The sync was reading **358 of 2,833 classes and reporting success.** The sheet writes its dates as
"January 2, 2026"; the reader understood "Jan 2, 2026" but not the full month name, and May is the
one month whose abbreviation is its own full name. So May parsed, the other eight months did not,
and 87% of the rows were dropped in silence. It had never been caught because the eight months of
history the system was built on came from a spreadsheet export rather than through this reader.

Both month forms are understood now, along with the raw serial number a spreadsheet stores
underneath. More importantly, dropping rows is counted by reason: losing more than a fifth of a tab
is an error, and a date the reader cannot read is always an error, whatever the share.

### Both formulas, on all 2,833 live classes

| | Karthika's formula | The new formula |
|---|---|---|
| Classes someone looks at | 254 | 415 |
| Per week | 7.1 | 11.5 |
| Of which video | 5.7 | 4.5 |

They disagree about 293 classes. Every one of the 227 that only the new formula sends was rated
below 4.6. Of the 66 that only Karthika's formula sends, 19 were rated 4.6 or better.
