# The timeline file

> Part of the `unity-play-harness` skill. One JSONL file per journey, written by
> `resources/JourneyRecorder.cs` and read by `scripts/journey_report.py`. The format exists so a
> run can be compared with another run — including one taken before a change.

## Layout on disk

```
<journey root>/                       persistentDataPath/journeys, or $JOURNEY_OUT
└── approach-gate/                    one directory per journey id, deleted and recreated per run
    ├── timeline.jsonl
    ├── 01_arrival.png                NN_<milestone>.png, windowed runs only
    └── 02_result.png
```

The directory is the unit: timeline and images from one run, nothing else. Mixing two runs in one
directory produces a set of images that describes a game that never existed.

## Three kinds of line

**Line 1 — meta.** Written in the constructor, before anything can go wrong, so a run that
crashes still says what it was:

```json
{"meta":true,"schema":1,"journey":"approach-gate","situation":"approach-gate","params":{"angle":"80"},"startedUtc":"2024-01-01T00:00:00Z","batch":false,"unity":"6000.0.0f1"}
```

**Lines 2..n — samples**, one per sampled frame, in order:

```json
{"n":0,"frame":412,"t":6.833,"ut":6.902,"dt":0.0167,"timeScale":1.000,"scene":"Run","situation":"approach-gate","state":"Approach","cam":"RunCam","pos":[0.000,1.200,-12.000],"vel":[0.000,0.000,9.800],"speed":9.800,"ready":{"gate":true,"laneMesh":true,"laneCollider":false,"sentry":true},"allReady":false,"counts":{"hazards":6,"pickups":3},"custom":{"lane":1,"gateDist":12.000},"milestone":null}
```

A sample with a `milestone` string is the tagged frame; everything else about it is a normal row,
which is what lets a report filter "the ten frames before arrival" without a second file.

**Last line — end.** Written by `Dispose`:

```json
{"end":true,"samples":74,"milestones":["arrival"]}
```

**A missing end line means the run did not finish.** That is a fact worth reading before the
numbers: `journey_report.py` says `end=missing` in its header rather than pretending the
recording is complete.

## Reading it by hand

```bash
head -1 timeline.jsonl                                        # what run was this
tail -1 timeline.jsonl                                        # did it finish, how many samples
grep -c . timeline.jsonl                                      # lines = samples + 2
python3 -c "import json,sys;[print(json.loads(l).get('state')) for l in open(sys.argv[1]) if '\"n\"' in l]" timeline.jsonl | uniq -c
```

The last one is the cheapest useful view there is: the state sequence with run lengths. A
`Launched` that appears twice, or an `Approach` lasting four frames, is visible in that output
and in no screenshot.

## The report

```bash
python3 scripts/journey_report.py --after approach-gate/timeline.jsonl \
  --monotonic state:Idle,Launched,Approach,AtGate \
  --max 'speed:12@gateDist<2' \
  --min pos.y:0 \
  --ready-before arrival \
  --together laneMesh,laneCollider \
  --no-null cam
```

| Flag | Asserts |
|---|---|
| `--monotonic state:A,B,C` | The key only moves forward through the listed values |
| `--max key:value` · `--min key:value` | A bound, over every sample the window admits |
| `@expr` on a bound | Narrows that one check to the samples matching the expression |
| `--window 'gateDist<2'` | The same narrowing applied to every `--max`, `--min` and `--ready-before` |
| `--ready-before NAME` | Every readiness member true at every sample up to that milestone |
| `--together a,b` | Two members flip to true in the same sample — the readiness-set rule, checked |
| `--no-null key` | The key is never null: a camera that disappeared, a state that went blank |

Key paths resolve in this order, so the short name usually works: exact dotted path (`pos.y`,
`custom.gateDist`, `ready.laneMesh`), then `custom.<name>`, then `counts.<name>`, then
`ready.<name>`. **A key that does not exist is a violation, not a crash** — a report that silently
checks nothing is the failure mode this whole skill is about.

Output:

```
[REPORT] violations=2 samples=74 journey=approach-gate situation=approach-gate end=ok
  params: angle=80
  max speed:12@gateDist<2   n=61   frame=473   t=7.850   speed=13.420
  together laneMesh,laneCollider  n=0  frame=412  t=6.833  laneMesh=true laneCollider=false

  key       median  p95     max     min    n
  gateDist  6.100   11.800  12.000  0.120  74
  speed     9.800   12.900  13.420  0.000  74
```

Exit 1 on any violation, 0 when clean, 2 on a usage or parse error. It is a CI step as written.

## Two runs, one table

```bash
python3 scripts/journey_report.py --before before/timeline.jsonl --after after/timeline.jsonl --max speed:12
```

adds a comparison column for every numeric key both runs have:

```
  key       stat     before    after     delta
  speed     median     9.80      8.40    -1.40
  speed     max       13.42     11.60    -1.82
  gateDist  min        0.12      0.14    +0.02
```

Compare the **same journey, same situation, same parameters**. The meta line carries all three,
and the report refuses to line up two timelines whose `journey` differs — comparing a cold-start
run with a warm one produces a table full of real-looking differences about nothing.

## Handing it to a person

The deliverable for a feel complaint is three things in one message, and no more:

1. **The sentence with numbers in it** — "entry speed at the gate, median 9.8 → 8.4, worst
   13.4 → 11.6 over 74 samples, budget 12".
2. **The two milestone screenshots**, before and after, same milestone, named so the pairing is
   obvious. → `unity-debug` → `reference/visual-checks.md`
3. **One question**: whether the new value is the feel they meant.

The table proves the change did what it claims. It does not prove the game feels right — that
judgement stays with the person who filed the complaint, and asking for it explicitly is how the
loop closes. → `reference/complaint-to-test.md`
