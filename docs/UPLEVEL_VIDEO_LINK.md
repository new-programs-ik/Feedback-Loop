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

## The automatic way: the form does it for you

Open **New analysis** from the queue (or fill the class name and date by hand) and the recording
is looked up on UpLevel by itself. What you see in the Recording box:

- **"Found in UpLevel and filled in."** One recording matches clearly. The Vimeo link is filled
  and the box shows the recording's full UpLevel name, date, type and length, so you can check at a
  glance that it is the right class. Not this one? "Other recordings" lists the next closest.
- **"N recordings match this class on the same day. Pick the right one."** Two cohorts, or a
  re-upload. Nothing is filled; you click **Use this** on the right one.
- **"No recording for this class in UpLevel yet."** Recordings appear a few hours after the class.
  Check the class name, date and instructor, or paste the link by hand.
- **"Automatic lookup is off"** or **"The UpLevel connection has expired."** Paste the link by hand
  (the steps are in the box); an admin reconnects UpLevel in two minutes (below).
- **"You changed the class details after the lookup."** The link may belong to a different class
  now; press **Search again**.

It never overwrites a link you typed yourself, and a live class is never matched to an assignment
review. If UpLevel cannot be reached it says so, never "no recording".

**How it matches.** The worker (`ratings_module_build_kit/uplevel.py`) reads UpLevel's Videos
table (`GET /get_videos/`, the same list the Videos page shows), searching by the instructor's
name and a word of the class name. Each row carries the Vimeo link, the clean class name
(`topic__name`), the length, and a `name` string with the instructor, the type and the date
(*"ML Architectures Live Class with Sarfaraz, …, Sunday, September 13, 2026 …"*). A recording on
a different day is ruled out; the rest are scored on instructor, class name and type, and come back
best first with the reasons in words.

**Proven on real data (22 September 2026).** *ML Architectures / Sarfaraz / 13 Sep* →
`vimeo.com/1226433411` and *MLOps – Model Training / Lakshaya / 13 Sep* → `vimeo.com/1226939172`,
both exact. A sweep of 30 recent classes matched all 30 on date, instructor and class name.
`test_uplevel.py` locks the parsing and matching offline.

---

## Connecting UpLevel (an admin, once every two weeks or so)

UpLevel has **no service token yet**, so the tool borrows a signed-in session. An admin connects it
on **Admin › UpLevel**:

1. In Chrome, sign in to UpLevel and open the **Videos** page.
2. Press **F12**, click **Network**, refresh the page.
3. Right-click any request › **Copy** › **Copy as cURL (bash)** (cmd, PowerShell or the raw headers
   also work).
4. Paste it into the box on Admin › UpLevel and press **Save and test**. It says "Connected".

Only two cookies are kept (`sessionid` and `csrftoken`); everything else in the paste, including
the refresh token, is thrown away. They are stored in `integration_credentials`, which nobody signed
in can read (migration 0032), and are never shown again. Never paste the request anywhere else,
including chat.

**How long it lasts.** What UpLevel checks is the `sessionid` (tested: the fetch kept working after
the one-hour login token inside the cookie had expired). It lasts **about two weeks, or until the
person who copied it logs out of UpLevel**. When it stops, Admin › UpLevel shows *Expired* and the
form says so; paste a fresh one. Nothing else breaks meanwhile: the form falls back to pasting the
link by hand.

**The permanent fix.** Ask the UpLevel platform team for a service account or a read-only API token
for the Videos list (or a documented refresh-token flow). When it exists, only one function in
`uplevel.py` (`_session()`) changes, and nobody has to paste anything again.

For local work only, `UPLEVEL_COOKIE` (environment) or `ratings_module_build_kit/uplevel-cookies.txt`
(gitignored) still work as fallbacks; what an admin saved in the app always wins.
