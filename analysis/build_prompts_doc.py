"""Write docs/THE_AI_ANALYSIS_PROMPTS.md from the prompts the engine actually uses.

The document used to be a hand-copied transcription of the prompts, so it drifted the moment the
engine changed - and after the September repairs almost every quoted block in it was wrong. It is
generated now: the explanation is written here, the prompt text is read from engine.py at build
time, and the two cannot disagree.

    python analysis/build_prompts_doc.py
"""
import datetime as dt
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import engine as E  # noqa: E402

OUT = os.path.join(ROOT, "docs", "THE_AI_ANALYSIS_PROMPTS.md")


def block(text):
    return "```text\n" + str(text).rstrip() + "\n```\n"


def flags(class_type):
    return ", ".join(f"`{f}`" for f in sorted(E.flags_for(class_type)))


L = []
w = L.append

w("# The AI analysis, opened up: the exact prompts we use")
w("")
w("Nothing here is paraphrased. Every block below is read straight out of `engine.py` when this")
w("file is generated, so it cannot drift from what the model is actually told. Regenerate it with")
w("`python analysis/build_prompts_doc.py` after any prompt change.")
w("")
w(f"Generated {dt.date.today():%d %B %Y} from the live engine. Model: `{E.CFG.model}`.")
w("")
w("---")
w("")

w("## 1. What runs, in order")
w("")
w("| Stage | What it does | Its budget |")
w("|---|---|---|")
w(f"| Materials | Turns whatever the PM attached into a plain outline. Skipped if nothing is attached. | {E.CFG.max_tokens_materials:,} tokens |")
w(f"| Video | Samples frames from the recording and describes what was on screen. Opt-in. | see `video.py` |")
w(f"| Session map | Reads the class and writes a neutral map: who spoke, the arc, what got resolved. | {E.CFG.max_tokens_map:,} tokens per part |")
w(f"| Extract | Reads each ~{E.CFG.window_min}-minute window and raises evidence-backed findings. | {E.CFG.max_tokens_extract:,} tokens |")
w(f"| Synthesise | Merges the findings, writes the feedback, and makes the re-class call. | {E.CFG.max_tokens_synth:,} tokens |")
w(f"| Self-check | An adversarial pass that tries to refute every serious finding. | {E.CFG.max_tokens_skeptic:,} tokens |")
w("| Reconcile | Rewrites the prose so it does not rest on a finding the self-check removed. | shares the synthesis budget |")
w("")
w("Two things about the session map are worth knowing, because both were wrong until September.")
w("")
w(f"It is built in consecutive parts of at most {E.CONV_MAP_MAX_CHARS:,} characters each, so the")
w("**whole** class is described. It used to be a single cut of the opening, which on a two-hour")
w("class covered the first seventy-nine minutes while every later stage was told it described the")
w("entire session.")
w("")
w("And a reply that hits its budget is now detected and re-asked for more compactly. A cut-off")
w("answer used to look exactly like a short one, so findings the model was still writing were lost")
w("without a trace.")
w("")
w("---")
w("")

w("## 2. The class context every stage sees")
w("")
w("Assembled by `build_context`. It states the rating honestly rather than assuming the class was")
w("bad, and when no agenda was supplied it says so and forbids the model from inventing one:")
w("")
w(block(E.build_context("Applied Generative AI", "Fine-Tuning & Domain Adaptation",
                        "A. Instructor", "4.11", "(not provided)", num_ratings="13")))
w("With an agenda supplied, the last block is replaced by the agenda itself.")
w("")
w("---")
w("")

w("## 3. The materials agent")
w("")
w(block(E.MATERIALS_MD_SYS))
w("---")
w("")

w("## 4. The session map")
w("")
w(block(E.CONV_MAP_SYS))
w("---")
w("")

w("## 5. Extraction: one window at a time")
w("")
w("The system prompt:")
w("")
w(block(E.EXTRACT_SYS))
w("The instruction that follows the rubric, for a live class with no video:")
w("")
_u = E.build_extract_user("(the class context from section 2)", "(the transcript window)",
                          "live_class", has_video=False)
w(block(_u[_u.find("WHICH LABEL"):]))
w("Note the first paragraph. The stage that chooses a label is now told which labels can lead to")
w("learners being asked to re-attend. It used to choose blind, and the choice between two")
w("neighbouring labels decided a re-teach.")
w("")
w("---")
w("")

w("## 6. The rubrics")
w("")
w(f"**Live class** ({len(E.FLAGS_LIVE)} flags): {flags('live_class')}")
w("")
w(block(E.RUBRIC_LIVE.replace("[[SECTION_C]]", "(section C, below)")
        .replace("[[SECTION_C_LIVE_ONLY]]", "").replace("[[SECTION_C_LIVE_ONLY_NOVIDEO]]", "")))
w(f"**Assignment review session** ({len(E.FLAGS_ARS)} flags): {flags('ars')}")
w("")
w(block(E.RUBRIC_ARS.replace("[[SECTION_C]]", "(section C, below)")
        .replace("[[SECTION_C_LIVE_ONLY]]", "").replace("[[SECTION_C_LIVE_ONLY_NOVIDEO]]", "")))
w("### Section C, which depends on whether we have the recording")
w("")
w("Without video:")
w("")
w(block(E.SECTION_C_TRANSCRIPT_ONLY.replace("[[SECTION_C_LIVE_ONLY_NOVIDEO]]",
                                            E.SECTION_C_LIVE_ONLY_NOVIDEO)))
w("With video:")
w("")
w(block(E.SECTION_C_WITH_VIDEO.replace("[[SECTION_C_LIVE_ONLY]]", E.SECTION_C_LIVE_ONLY)))
w("The lines naming `slides_mismatch` and `coding_time` appear only for a live class, because a")
w("test review cannot return those flags. Asking for them there used to make the model produce a")
w("finding the validator rejected, which cost one retry and then the whole class analysis.")
w("")
w("---")
w("")

w("## 7. The severity bars")
w("")
w(block(E.SEVERITY_ANCHORS))
w("Two of these are enforced in code, not only asked for. In an assignment review a `correctness`")
w("finding is raised to major if it arrives below that, and it can only be dropped on a stated")
w("attribution or evidence failure, never on an opinion about how serious it was.")
w("")
w("---")
w("")

w("## 8. Synthesis: verify, write, and call the re-class")
w("")
w(block(E.SYNTH_SYS))
w("The re-class rule differs by class kind. For a live class:")
w("")
_s = E.build_synth_user("(context)", "[]", "live_class")
_i = _s.find('- "yes"')
_j = _s.find("The PM makes the final call.", _i)
w(block(_s[_i:_j + len("The PM makes the final call.")]))
w("A `yes` must also survive two code checks it cannot argue with: at least one surviving major")
w("finding among")
w(f"{', '.join('`' + f + '`' for f in sorted(E.content_delivery_flags('live_class')))} for a live")
w(f"class, or {', '.join('`' + f + '`' for f in sorted(E.content_delivery_flags('ars')))} for a")
w("review; and that finding must not be one the model itself marked low confidence.")
w("")
w("---")
w("")

w("## 9. The self-check")
w("")
w(block(E.SKEPTIC_SYS))
w("It can uphold, downgrade or drop. It cannot raise a severity and it cannot add a finding, which")
w("is deliberate: it exists to remove false alarms. The consequence is that recall has to be right")
w("at extraction, because nothing downstream can recover something that was never raised.")
w("")
w("---")
w("")

w("## 10. Reconciling the prose afterwards")
w("")
w(block(E.RECONCILE_SYS))
w("When this fails, the draft is marked as not tidied rather than shipped as though it were. The")
w("re-class reason also carries a short line written by the code stating exactly what survived, so")
w("a sentence that understates the findings cannot mislead on its own.")
w("")
w("---")
w("")

w("## 11. Revise with AI, on the review page")
w("")
w("Rewriting the internal note:")
w("")
w(block(E.REVISE_SYS))
w("Rewriting the note that goes to the instructor:")
w("")
w(block(E.REVISE_SUMMARY_SYS))
w(f"That note is capped at {E.SUMMARY_MAX_BULLETS} points. The points are ordered by the severity")
w("of the finding behind them before the cap is applied, so the serious one is not deleted to make")
w("room for notes about the camera. The re-teach decision is stripped out of it in code.")
w("")
w("---")
w("")
w("## 12. Suggesting a change")
w("")
w("Prompt changes are code changes: edit the constant in `ratings_module_build_kit/engine.py`, run")
w("`python -m unittest` in that folder, and regenerate this file. If you want a different tone or a")
w("new thing checked, open an issue describing the behaviour you want and the class that made you")
w("want it.")
w("")

with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print(f"wrote {OUT} ({len(L)} lines)")
