# How we will decide which formula is right

Written before the analysis was re-run, on purpose. Once the results are in it is easy to pick the
measure that flatters the answer you already like, so the measure is fixed here first.

## What the two formulas disagree about

Both give a class a score out of 100 and a band. They disagree about which classes a person should
look at. The twelve classes chosen for this test are the ones where they disagree most, in both
directions.

- **Test A** — the new formula says watch the recording, the old one says nobody needs to look.
- **Test B** — the old formula says spend a video on it, the new one says it is not needed.

## The measure

The video analysis answers two different questions, and only one of them was being counted before.

**Question 1, the narrow one: does this class need to be taught again?**
That is the re-class call. It is a very high bar by design: a whole cohort re-attending a repeated
class. It requires a major failure of content that survived an adversarial check.

**Question 2, the one the queue is actually for: was there anything here worth telling someone?**
A class can be delivered without a re-teach being warranted and still contain a wrong definition, a
skipped exercise or a doubt left hanging. Those are the things a PM sends to an instructor.

We count both, separately, and we say which is which.

## What counts as a hit, per class

| | Test A (new formula said look) | Test B (old formula said look) |
|---|---|---|
| The analysis asks for a re-teach ("yes") | new formula was right | old formula was right |
| A content problem at moderate or worse survives verification — a wrong statement, a planned item not delivered, a solution not walked through | new formula was right | old formula was right |
| Only presentation notes survive — pace, camera, screen share, dead air, low interaction | old formula was right: nobody needed to look | new formula was right: the video was not needed |
| Nothing survives at all | old formula was right | new formula was right |

"Content problem" means a surviving finding whose flag is one of `correctness`, `coverage`,
`problem_coverage` or `solution_walkthrough`, at moderate or major severity. Those are the four the
engine already treats as the ones that decide a re-teach, so the definition is not invented for this
test.

## Rules we hold ourselves to

1. **A result from an analysis whose self-check did not run does not count.** It is re-run instead.
   The engine now records this, so it cannot be missed.
2. **A class whose analysis lost a window does not count** until it is re-run. The engine now
   records that too.
3. **The re-class call is reported as it comes.** If it is softened, both the original and the
   softened call are shown, with the reason.
4. **Every class is listed, including the ones that go against the new formula.** The count of
   classes where the new formula was wrong is stated as plainly as the count where it was right.
5. **One run per class.** The engine has been shown to answer differently on repeat runs; that is
   the honest caveat on the whole exercise and it is stated in the report, not hidden by picking a
   favourable run.
6. **If the two formulas come out level, the simpler one wins.** A change has to earn its place.

## What would make us keep the old formula

Any one of these:

- Test A produces no content problems worth acting on. The new formula would then be sending people
  to watch recordings for nothing.
- Test B produces content problems in most classes. The old formula would then be catching things
  the new one waves through.
- The new formula's extra work does not fit the team's capacity, and no band edge brings it under
  without hiding a real problem.

## What would make us keep the new formula

- Test A produces content problems that the old formula would have left unseen.
- Test B produces nothing but presentation notes, meaning the old formula spends videos it does not
  need to.

## The honest limit of this test

Twelve classes is a small sample, and the analysis is not perfectly repeatable. This test can show
a clear pattern; it cannot settle the question to a decimal place. Whatever it shows, the report
says how many classes it rests on.
