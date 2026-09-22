# Getting a class's recording link from UpLevel

Every class we analyse needs its **Vimeo link** — the recording. That link lives in IK's UpLevel.
This page has two parts: the **manual way** anyone on the team can follow, and the **automatic way**
the tool now does the same search for you.

Both do the same thing a person does by hand: find the recording whose **class name, date and
instructor** match the class, and read off its Vimeo link. A recording on a different day is a
different class, so the date has to line up.

---

## The manual way (anyone, no code)

1. Sign in to **UpLevel** → open the **Videos** page
   (`https://uplevel.interviewkickstart.com/videos/`).
2. In the search box, type the **instructor's name** (one word is enough, e.g. `Sarfaraz`), or a
   distinctive word from the class name.
3. In the list, find the row that matches on all three:
   - **Class name** (e.g. *ML Architectures*),
   - **Date** (e.g. *Sunday, September 13, 2026*),
   - **Category** — pick the right one: **Live Class**, **Assignment Review Class**, or
     **Technical Coaching Class**. A live class and its assignment review can share a name and a
     week, so this matters.
4. Click **Play** on that row, or open it, and copy the **Vimeo link**
   (looks like `https://vimeo.com/1226433411`).
5. Paste that link into the **New analysis** form in Feedback Loop.

That is the whole job: match name + date + instructor + category, take the link.

---

## The automatic way (built into the worker)

`ratings_module_build_kit/uplevel.py` does the same search. Given a class's topic, instructor,
date and kind, it reads UpLevel's Videos table, ranks the recordings that could be this class, and
returns the best one **with the reasons in words** (same date, instructor matches, class name
matches, category matches). The caller shows that to a PM, who confirms before it is used —
exactly like checking it yourself. It never guesses silently, and when it cannot reach UpLevel it
says "could not look it up", never "no recording".

**How it works underneath.** UpLevel's Videos page is a table served by `GET /get_videos/`
(a DataTables endpoint: `search[value]=<one word>`, plus `draw`, `start`, `length`). Each row is
one recording: `vimeo_link`, `topic__name` (the clean class name), `duration_in_sec`, and a `name`
string that carries the instructor, the category and the date
(*"ML Architectures Live Class with Sarfaraz, …, Sunday, September 13, 2026 …"*). The module
searches by the instructor's name, parses the date and category out of each `name`, compares the
class name, and scores the fit.

**Proven on real data (22 September 2026).** Two classes we already knew were checked and matched
exactly: *ML Architectures / Sarfaraz / 13 Sep* → `vimeo.com/1226433411`, and
*MLOps – Model Training / Lakshaya / 13 Sep* → `vimeo.com/1226939172`. A sweep of 30 recent classes
matched all 30, every one on the same date with the instructor and class name agreeing. Some
classes have more than one recording on the same day (two cohorts, or a re-upload); those come back
as several candidates and the PM picks the right one — which is why the confirm step exists.

**Tests.** `test_uplevel.py` locks the parsing and the matching offline (no session needed).

---

## The one thing still needed: a durable login

UpLevel is a Django app behind AWS Cognito. There is **no service token yet**, so today the worker
borrows a **signed-in browser session**:

- Sign in to UpLevel in Chrome, open the Videos page, DevTools → Network → right-click any request
  → **Copy as cURL (bash)**.
- Put that in the `UPLEVEL_COOKIE` environment variable on the worker (a full cookie header
  string), or, for local work, save it in `ratings_module_build_kit/uplevel-cookies.txt`
  (gitignored, never committed).

**This is temporary.** A browser session lasts at most about a day and dies when the person logs
out, and the Cognito tokens inside it expire within the hour. A button the whole team uses cannot
depend on one person's session. **Ask the platform team for one of:** a service account or API
token for the Videos endpoints, or a documented refresh-token flow. When that exists, only one
function in `uplevel.py` (`_session()`) changes — nothing else. Until then, treat automatic
fetching as a convenience that may need the session refreshed, and the manual way above as the
fallback that always works.
