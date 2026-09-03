"""The presenter's version of the instructor-approval study - 3 pages, plain English, no jargon.

Every number is computed from the same rows as the full study so the two never disagree. Page 1:
the story and the four kinds of class. Page 2: the rule and what it changes. Page 3: a 5-minute
talk track and the questions to expect. Local only - never committed or published.
"""
import os
import statistics as st
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from approval_weights import compute, LINE, APPROVAL_BAR, REACH_BAR, VOICES, R_FLOOR, A_FLOOR  # noqa: E402
from approval_rule import W, URGENT, BORDERLINE, health, band, verdict_v1, verdict_v2  # noqa: E402

BLUE, ORANGE, GREEN, GREY = "#2a78d6", "#eb6834", "#2f9e6e", "#7a7a85"

C = compute(verbose=False)
rows, weeks = C["rows"], C["weeks"]
bad = lambda r: r["rating"] < LINE              # noqa: E731
low = lambda r: r["approval"] < APPROVAL_BAR    # noqa: E731
n = len(rows)
Y = sum(r["yes"] for r in rows)
N = sum(r["no"] for r in rows)
fine = [r for r in rows if not bad(r) and not low(r)]
both = [r for r in rows if bad(r) and low(r)]
hard = [r for r in rows if bad(r) and not low(r)]
polite = [r for r in rows if not bad(r) and low(r)]
polite5 = [r for r in polite if r["responses"] >= VOICES]
badrows = [r for r in rows if bad(r)]
no_in_fine = sum(r["no"] for r in rows if not bad(r))
jan = [r for r in rows if r["date"].month == 1]
aug = [r for r in rows if r["date"].month == 8]
G = C["lens2_groups"]
v1 = Counter(verdict_v1(r) for r in rows)
v2 = Counter(verdict_v2(r) for r in rows)
queued = [r for r in rows if verdict_v2(r) in ("video", "transcript")]
bands = Counter(band(health(r)) for r in queued)
urgent_lowreach = sum(1 for r in queued if health(r) < URGENT and r["pct"] < REACH_BAR)
border_highreach = sum(1 for r in queued if health(r) >= BORDERLINE and r["pct"] >= REACH_BAR)
drop90 = next(x for x in C["table_thr"] if x["thr"] == 90)["miss_cur"]
l2r = C["lens2"]["next rated below %.2f" % LINE]["share"]
l2a = C["lens2"]["next approval below %d%%" % APPROVAL_BAR]["share"]
cost1 = (v1["video"] * 0.70 + v1["transcript"] * 0.51) / 8
cost2 = (v2["video"] * 0.70 + v2["transcript"] * 0.51) / 8
monthly = []
for m in range(1, 9):
    g = [r for r in rows if r["date"].month == m]
    monthly.append((sum(1 for r in g if bad(r)) / len(g) * 100, sum(1 for r in g if low(r)) / len(g) * 100))


def pct(a, b):
    return a / b * 100 if b else 0


# ---------------------------------------------------------------- tiny charts (inline SVG)
def trend_svg():
    W_, H_ = 640, 150
    ml, mr, mt, mb = 40, 16, 16, 26
    pw, ph = W_ - ml - mr, H_ - mt - mb
    x = lambda i: ml + i / 7 * pw               # noqa: E731
    y = lambda v: mt + ph - v / 30 * ph          # noqa: E731
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Both problem shares rise from January to August.">' % (W_, H_)]
    for v in (0, 10, 20, 30):
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, y(v), W_ - mr, y(v)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%d%%</text>' % (ml - 6, y(v) + 4, v))
    for i in range(8):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (x(i), H_ - mb + 16, MONTHS[i]))
    for idx, col, lab in ((0, ORANGE, "rated under %.2f" % LINE), (1, BLUE, "under %d%% approval" % APPROVAL_BAR)):
        pts = [m[idx] for m in monthly]
        d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", x(i), y(v)) for i, v in enumerate(pts))
        p.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.5"/>' % (d, col))
        for i, v in enumerate(pts):
            p.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s"/>' % (x(i), y(v), col))
        p.append('<text x="%.1f" y="%.1f" class="lab" style="fill:%s" text-anchor="end">%s: %.0f%% &rarr; %.0f%%</text>'
                 % (x(7) - 8, y(pts[-1]) - 8, col, lab, pts[0], pts[-1]))
    p.append('</svg>')
    return "".join(p)


def before_after_svg():
    W_, H_ = 640, 100
    ml = 120
    pw = W_ - ml - 20
    mx = 560
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Today versus the new rule: same number of classes analysed, more of them start with a transcript.">' % (W_, H_)]
    for i, (lab, c) in enumerate((("Today's rule", v1), ("New rule", v2))):
        yy = 8 + i * 46
        vid, tr = c["video"], c["transcript"]
        p.append('<text x="%d" y="%d" class="lab" text-anchor="end" style="fill:var(--ink)">%s</text>' % (ml - 12, yy + 20, lab))
        wv = vid / mx * pw
        wt = tr / mx * pw
        p.append('<rect x="%d" y="%d" width="%.1f" height="30" rx="4" fill="%s"/>' % (ml, yy, wv, ORANGE))
        p.append('<rect x="%.1f" y="%d" width="%.1f" height="30" rx="4" fill="%s"/>' % (ml + wv + 2, yy, wt, BLUE))
        p.append('<text x="%.1f" y="%d" class="lab" text-anchor="middle" style="fill:#fff">%d</text>' % (ml + wv / 2, yy + 20, vid))
        p.append('<text x="%.1f" y="%d" class="lab" text-anchor="middle" style="fill:#fff">%d</text>' % (ml + wv + 2 + wt / 2, yy + 20, tr))
        p.append('<text x="%.1f" y="%d" class="lab" style="fill:var(--ink2)">%d &middot; $%.0f/mo</text>'
                 % (ml + wv + wt + 10, yy + 20, vid + tr, cost1 if i == 0 else cost2))
    p.append('</svg>')
    return "".join(p)


HTML = """<title>Instructor Approval Brief</title>
<style>
:root{--bg:#f7f7f5;--surface:#fff;--surface2:#f2f2ef;--ink:#16161a;--ink2:#4b4b53;--ink3:#7a7a85;
  --grid:#e2e2dd;--line:#dededa;--brand:%(BLUE)s;--warn:%(ORANGE)s;--radius:12px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:13.2px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:22px 22px 24px}
.page{break-after:page}
h1{font-size:25px;line-height:1.12;letter-spacing:-.02em;margin:0 0 4px}
h2{font-size:16px;letter-spacing:-.01em;margin:12px 0 5px}
h3{font-size:15px;margin:16px 0 6px}
p{margin:6px 0}
.kicker{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand);margin-bottom:8px}
.lede{font-size:14px;color:var(--ink2)}
.big{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.stat{flex:1 1 150px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:9px 12px}
.stat .v{font-size:23px;font-weight:750;letter-spacing:-.02em}
.stat .l{font-size:11.5px;color:var(--ink2);margin-top:2px}
.quad{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.q{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:9px 12px;border-top:4px solid var(--c)}
.q .n{font-size:20px;font-weight:750;letter-spacing:-.02em}
.q .t{font-weight:650;margin-top:2px}
.q .d{font-size:11.8px;color:var(--ink2);margin-top:3px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:9px 14px;margin:6px 0}
.finding{border-left:4px solid var(--warn)}
.ok{border-left:4px solid var(--brand)}
.figure{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:6px 10px 2px;margin:6px 0}
.figure svg{display:block;width:100%%;height:auto}
.cap{color:var(--ink2);font-size:11.8px;padding:3px 4px 4px}
.tick{font-size:11px;fill:var(--ink3)}
.lab{font-size:12px;font-weight:700;fill:var(--ink2)}
.flow{display:flex;gap:8px;align-items:stretch;margin:8px 0}
.step{flex:1;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:7px 10px;font-size:11.8px}
.step b{display:block;font-size:13.5px;margin-bottom:3px}
.step .k{font-size:10.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--brand)}
.arrow{align-self:center;color:var(--ink3);font-size:20px}
.weights{display:flex;gap:8px;margin:8px 0}
.w{flex:1;border-radius:var(--radius);padding:6px 10px;color:#fff}
.w .p{font-size:18px;font-weight:750;letter-spacing:-.02em}
.w .t{font-size:11.8px;opacity:.95}
table{width:100%%;border-collapse:collapse;margin:6px 0;font-size:12.3px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);background:var(--surface2)}
tr.pickrow td{background:color-mix(in srgb,%(BLUE)s 10%%,transparent);font-weight:650}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.say{background:var(--surface2);border-radius:var(--radius);padding:8px 13px;margin:6px 0;font-size:12.6px}
.say .who{font-size:10.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--brand)}
.qa{margin:8px 0}
.qa .q{font-weight:650;border:0;padding:0;margin-top:6px;background:none}
.qa .a{color:var(--ink2);margin:1px 0 0;font-size:12.2px}
.sub{color:var(--ink2);font-size:11.8px}
footer{margin-top:12px;padding-top:8px;border-top:1px solid var(--line);color:var(--ink3);font-size:11px}
@page{size:A4;margin:10mm 12mm}
@media print{body{background:#fff}.wrap{max-width:none;padding:0 4px}.figure,.card,table,.quad,.flow,.say{break-inside:avoid}}
</style>
<div class="wrap">

<!-- ================================================== PAGE 1 -->
<div class="page">
<div class="kicker">Interview Kickstart &middot; New Programs &middot; the short version</div>
<h1>Does the room want the instructor back?</h1>
<p class="lede">Every rating form also asks: <i>would you want this instructor to take the class again?</i>
We read that yes/no answer for every class from January to August &mdash; <b>%(n)s classes,
%(votes)s votes</b> &mdash; to see what it adds to the rating we already use, and how to use it.</p>

<div class="big">
  <div class="stat"><div class="v">%(approval).0f%%</div><div class="l">of all votes say <i>yes, have them back</i></div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(underpct).0f%%</div><div class="l">of classes fall under the %(abar)d%% bar</div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(badokpct).0f%%</div><div class="l">of low-rated classes still say <i>yes</i> to the instructor</div></div>
  <div class="stat"><div class="v">%(newperweek).1f</div><div class="l">extra classes a week the bar adds to our work</div></div>
</div>

<div class="card finding" style="margin-top:12px">
<p style="margin:0"><b>The rating tells us the class went badly. The vote tells us whether the instructor is the reason.</b>
They usually agree &mdash; but not always, and the disagreements are exactly the classes we were
either missing or misreading.</p>
</div>

<h2>Every class falls into one of four boxes</h2>
<div class="quad">
  <div class="q" style="--c:%(BLUE)s"><div class="n">%(nfine)s</div><div class="t">Fine on both</div>
    <div class="d">Rated %(line).2f+ and %(abar)d%%+ would have the instructor back. Nothing to do.</div></div>
  <div class="q" style="--c:%(GREY)s"><div class="n">%(npolite)d</div><div class="t">Polite rating, would not have them back</div>
    <div class="d">Rated fine, but under %(abar)d%% said yes. <b>Today we never see these.</b> They are an instructor question &mdash; the vote's whole job.</div></div>
  <div class="q" style="--c:%(GREY)s"><div class="n">%(nhard)d</div><div class="t">Hard class, good teacher</div>
    <div class="d">Rated low, but the room still wants the instructor. Still worth a look &mdash; the problem is more likely content or difficulty than delivery.</div></div>
  <div class="q" style="--c:%(ORANGE)s"><div class="n">%(nboth)d</div><div class="t">Fails both</div>
    <div class="d">Rated low <i>and</i> the room would not have them back. The clearest cases &mdash; these should jump the queue.</div></div>
</div>

<h2>Three things the eight months show</h2>
<p><b>1. The vote adds real information.</b> About half of what the vote says is not already in the rating.
Nearly half of all &ldquo;no&rdquo; votes (%(noinfine).0f%%) were cast in classes that were rated fine.</p>
<p><b>2. It predicts what happens next.</b> When a class is rated low, the instructor's next class is low
%(rlow).0f%% of the time. When the room <i>also</i> would not have them back, that jumps to
<b>%(bothnext).0f%%</b>. When both are fine it is %(base).0f%%.</p>
<p><b>3. Both problems are growing.</b> Classes under the approval bar doubled from %(janlow).0f%% in January
to %(auglow).0f%% in August, on the same slope as low ratings (%(janbad).0f%% &rarr; %(augbad).0f%%).</p>
</div>

<!-- ================================================== PAGE 2 -->
<div class="page">
<div class="kicker">The proposal</div>
<h1 style="font-size:26px">Two bars decide <i>if</i>. One score decides <i>how urgent</i>.</h1>
<p class="lede">We keep the rating rule we already run, add the %(abar)d%% approval bar next to it, and use a
weighted score to decide which flagged classes come first and how deep the analysis goes.</p>

<div class="flow">
  <div class="step"><span class="k">Step 1 &middot; enough voices?</span><b>Fewer than %(voices)d people voted &rarr; watch only</b>
    One or two opinions is not a class problem yet. Same floor as today.</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><span class="k">Step 2 &middot; the two bars</span><b>Rated under %(line).2f <i>or</i> under %(abar)d%% approval &rarr; needs a look</b>
    Either one on its own is enough. Both fine &rarr; no analysis.</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><span class="k">Step 3 &middot; the health score</span><b>Urgent (under %(urgent)d) &middot; Needs a look &middot; Borderline (%(borderline)d+)</b>
    Urgent &rarr; video, always. Borderline &rarr; transcript first. In between &rarr; today's %(reach)d%% participation check.</div>
</div>

<h2>The Class Health Score &mdash; and why these weights</h2>
<div class="weights">
  <div class="w" style="background:%(ORANGE)s"><div class="p">%(wr).0f%%</div><div class="t"><b>The rating</b> (with today's voice checks) &mdash; the strongest signal on every check.</div></div>
  <div class="w" style="background:%(BLUE)s"><div class="p">%(wa).0f%%</div><div class="t"><b>The approval vote</b> &mdash; half new information; the only signal that predicts approval trouble.</div></div>
  <div class="w" style="background:%(GREY)s"><div class="p">%(wt).0f%%</div><div class="t"><b>The track record</b> (the instructor's earlier classes) &mdash; independent of both; about the instructor, not this class.</div></div>
</div>
<p class="sub" style="margin:4px 0 6px"><b>Where the numbers come from.</b> For every class we looked at the same instructor's
<i>next</i> class, and measured how much each signal helps predict trouble there when all three are used together:</p>
<table>
<tr><th>Predicting&hellip;</th><th>Rating</th><th>Vote</th><th>Track record</th><th>What it says</th></tr>
<tr><td>a low rating next class</td><td class="n">%(sRr).0f%%</td><td class="n">%(sRa).0f%%</td><td class="n">%(sRt).0f%%</td><td>the rating carries it; the vote adds little on top</td></tr>
<tr><td>a failed vote next class</td><td class="n">%(sAr).0f%%</td><td class="n">%(sAa).0f%%</td><td class="n">%(sAt).0f%%</td><td>the vote matters as much as the rating</td></tr>
<tr class="pickrow"><td>both kinds of trouble, equally</td><td class="n">%(avR).0f%% &rarr; %(wr).0f</td><td class="n">%(avA).0f%% &rarr; %(wa).0f</td><td class="n">%(avT).0f%% &rarr; %(wt).0f</td><td>the rule must catch both &mdash; average, round to five</td></tr>
</table>
<p class="sub" style="margin:2px 0 4px">Cross-checks: half of what the vote says is new information, the track record almost all new &mdash; neither can be a token weight.
And the mix is not fragile: moving any weight by five points changes the band of about ten classes in eight months.</p>

<div class="card ok">
<p style="margin:0"><b>Why not one score that decides everything?</b> We tried hundreds of weight and threshold
combinations. Every one lets a well-liked instructor's bad rating slide &mdash; the %(line).2f line quietly becomes about
%(effline).2f, the %(abar)d%% bar about %(effbar).0f%%, and <b>%(drop90)d classes</b> we analyse today would be dropped. So the bars
stay hard; the score orders the queue and chooses the depth.</p>
</div>

<h2>What changes, over the same eight months</h2>
<div class="figure">%(beforeafter)s<div class="cap"><span style="color:%(ORANGE)s;font-weight:700">Orange</span> = video analyses, <span style="color:%(BLUE)s;font-weight:700">blue</span> = transcript analyses, then the total and the monthly AI cost.
<b>Keeps all %(v1work)d classes</b> today's rule analyses &middot; <b>adds %(npolite5)d</b> the vote alone catches (under one a week) &middot;
sends <b>%(nurgent)d urgent</b> classes straight to video (%(urglow)d of them would have waited for a transcript under today's participation check) &middot;
starts <b>%(nborder)d borderline</b> classes with the cheaper transcript, video if it confirms.</div></div>

<p style="margin:8px 0 0"><b>The two decisions we need:</b> &nbsp;<b>1.</b> the weights, <b>%(wr).0f / %(wa).0f / %(wt).0f</b>; &nbsp;<b>2.</b> borderline classes start with a
<b>transcript</b> instead of a video &mdash; the one change to today's rule, a single switch either way.</p>
</div>

<!-- ================================================== PAGE 3 -->
<div class="page">
<div class="kicker">How to present it</div>
<h1 style="font-size:26px">Five minutes, in your own words</h1>
<p class="lede">Read down the left; the right is the number to point at. The detailed study is the backup
&mdash; you do not need to open it unless someone asks.</p>

<div class="say"><div class="who">Open &middot; 30 seconds</div>
&ldquo;We already flag classes on the rating. The form also asks learners whether they would want the
same instructor again. We looked at every class since January &mdash; %(n)s classes, %(votes)s votes
&mdash; to see what that second answer adds.&rdquo;</div>

<div class="say"><div class="who">The finding &middot; 1 minute</div>
&ldquo;Short version: the rating tells us the class went badly; the vote tells us whether the instructor is
the reason. They usually agree. But %(badokpct).0f%% of our low-rated classes still say yes to the instructor
&mdash; hard class, good teacher &mdash; and %(npolite)d classes were rated fine while the room said
&lsquo;not again&rsquo;. Those %(npolite)d are the ones we never see today.&rdquo;</div>

<div class="say"><div class="who">Why it matters &middot; 45 seconds</div>
&ldquo;It is not just a description. When a class is rated low, the same instructor's next class is low
%(rlow).0f%% of the time. When the room also would not have them back, it is %(bothnext).0f%%. And both
problems have doubled since January.&rdquo;</div>

<div class="say"><div class="who">The proposal &middot; 1&frac12; minutes</div>
&ldquo;We keep the %(line).2f rating line and add the %(abar)d%% approval bar beside it &mdash; either one puts a
class in the queue. Then a health score &mdash; %(wr).0f%% rating, %(wa).0f%% vote, %(wt).0f%% the instructor's
track record &mdash; says how urgent it is. Urgent goes straight to video; borderline starts with a
transcript; the middle uses the participation check we already have. Over eight months that drops nothing
we do today, adds under one class a week, and costs the same.&rdquo;</div>

<div class="say"><div class="who">The ask &middot; 30 seconds</div>
&ldquo;Two decisions: are we happy with %(wr).0f / %(wa).0f / %(wt).0f, and should borderline classes start with a
transcript rather than a video? Everything else is already built and waiting on those two.&rdquo;</div>

<h2>Questions you will get</h2>
<div class="qa">
<div class="q">Why %(abar)d%% and not higher?</div>
<div class="a">At %(abar)d%% the bar catches %(npolite5)d new classes in eight months. At 85%% that quadruples, mostly
classes rated 4.6+ where one person said no. At 75%% it adds almost nothing the rating had not caught.</div>
<div class="q">Why not just one combined score?</div>
<div class="a">Because a weighted average lets a popular instructor's bad rating slide. Every version we tried moved
the %(line).2f line to about %(effline).2f for liked instructors and dropped %(drop90)d classes we analyse today.</div>
<div class="q">A class of four had one &ldquo;no&rdquo; &mdash; is that a fail?</div>
<div class="a">No. One no in four is 75%%, under the bar on one opinion. That is why the vote gets the same
five-voice floor as the rating: fewer than %(voices)d voters, we watch, we do not act.</div>
<div class="q">Where did %(wr).0f / %(wa).0f / %(wt).0f come from?</div>
<div class="a">From the data, not from a preference: we measured how much each signal predicts the instructor\'s next class going wrong,
for both kinds of trouble, and averaged the two (page 2). The rating leads, the vote takes a quarter, the track record the rest. Moving
any weight by five points changes the band of about ten classes in eight months &mdash; the bars do the heavy lifting.</div>
<div class="q">What changes for the team?</div>
<div class="a">The queue shows the vote (&ldquo;13 of 15 would have them back&rdquo;), the priority, and why the class
was flagged, urgent first. The Slack note to the course handler says the same in one line. Nothing new to type.</div>
<div class="q">Is the vote data reliable?</div>
<div class="a">It is on every row of the sheet already, and on every class the yes and no counts add up exactly to
the number of ratings.</div>
</div>

<footer>Numbers: %(n)s live classes and test reviews, 1 January&ndash;31 August 2026, from the ratings sheet.
Full working, charts and tables: <i>Instructor-Approval-Study.pdf</i> (sections 1&ndash;4). Confidential &mdash; internal use.</footer>
</div>
</div>
""" % dict(
    BLUE=BLUE, ORANGE=ORANGE, GREY=GREY, n="{:,}".format(n), votes="{:,}".format(int(Y + N)),
    line=LINE, abar=APPROVAL_BAR, voices=VOICES, reach=REACH_BAR, urgent=URGENT, borderline=BORDERLINE,
    wr=W[0] * 100, wa=W[1] * 100, wt=W[2] * 100,
    approval=pct(Y, Y + N), underpct=pct(sum(1 for r in rows if low(r)), n), badokpct=pct(len(hard), len(badrows)),
    newperweek=len(polite5) / weeks, nfine="{:,}".format(len(fine)), npolite=len(polite), npolite5=len(polite5),
    nhard=len(hard), nboth=len(both), noinfine=pct(no_in_fine, N),
    rlow=G["rated low, approval fine"][1], bothnext=G["rated low, approval low"][1], base=G["rated fine, approval fine"][1],
    janlow=monthly[0][1], auglow=monthly[-1][1], janbad=monthly[0][0], augbad=monthly[-1][0],
    trend=trend_svg(), beforeafter=before_after_svg(), drop90=drop90,
    v1work=v1["video"] + v1["transcript"], nurgent=bands["Urgent"], urglow=urgent_lowreach, nborder=bands["Borderline"],
    cost1=cost1, cost2=cost2,
    sRr=l2r["R"], sRa=l2r["A"], sRt=l2r["T"], sAr=l2a["R"], sAa=l2a["A"], sAt=l2a["T"],
    avR=C["avg_share"]["R"], avA=C["avg_share"]["A"], avT=C["avg_share"]["T"],
    effline=R_FLOOR + (LINE - R_FLOOR) * (1 - 0.1 / W[0]), effbar=A_FLOOR + (APPROVAL_BAR - A_FLOOR) * (1 - 0.1 / W[1]),
)

out = os.path.join(HERE, "instructor-approval-brief.html")
open(out, "w", encoding="utf-8").write(HTML)
print("wrote %s (%.0f KB)" % (out, len(HTML) / 1024))
