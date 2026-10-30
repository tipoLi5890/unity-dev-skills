# targets: skills/unity-play-harness/scripts/journey_report.py, skills/unity-gameplay/scripts/jump_report.py, skills/unity-camera/scripts/camera_jitter.py
def resolve(sample, key):
    """Value of `key` in one timeline/1 sample, or MISSING. One order, pasted unchanged into
    journey_report.py, jump_report.py and camera_jitter.py: pos.x|y|z and vel.x|y|z (or .0 to .2),
    then an exact dotted path (custom.gateDist, ready.laneMesh), then custom.<key>, counts.<key>,
    ready.<key>, then a top-level field."""
    if "." in key:
        head, rest = key.split(".", 1)
        if head in ("pos", "vel"):
            vec = sample.get(head)
            idx = {"x": 0, "y": 1, "z": 2, "0": 0, "1": 1, "2": 2}.get(rest)
            if isinstance(vec, list) and idx is not None and idx < len(vec):
                return vec[idx]
            return MISSING
        container = sample.get(head)
        if isinstance(container, dict) and rest in container:
            return container[rest]
        return MISSING
    for bucket in ("custom", "counts", "ready"):
        container = sample.get(bucket)
        if isinstance(container, dict) and key in container:
            return container[key]
    if key in sample:
        return sample[key]
    return MISSING


def stamp_problems(path, meta, samples, end):
    """(warnings, errors) for the timeline/1 stamp. A meta line stamped "timeline/1" must carry
    what the schema requires (journey; n, frame and t on every sample unless it is
    {"n": k, "playing": false}; samples and milestones on the end line, samples counted right):
    a miss is a writer bug and an error. The 0.34 stamp `"schema": 1` is read as timeline/1 with
    one warning, for one release; no stamp, or another one, is read the same way with a warning."""
    stamp = meta.get("schema") if isinstance(meta, dict) else None
    if stamp == "timeline/1":
        errors = []
        if not meta.get("journey"):
            errors.append("%s: the meta line has no journey" % path)
        for s in samples:
            need = ("n",) if s.get("playing") is False else ("n", "frame", "t")
            lost = [k for k in need if k not in s]
            if lost:
                errors.append("%s: sample n=%s has no %s" % (path, s.get("n"), ", ".join(lost)))
                break
        if end is not None:
            if "samples" not in end or "milestones" not in end:
                errors.append("%s: the end line needs samples and milestones" % path)
            elif end["samples"] != len(samples):
                errors.append("%s: the end line counts %s samples, the file has %d"
                              % (path, end["samples"], len(samples)))
        return [], errors
    if stamp == 1 and not isinstance(stamp, bool):
        return ["WARN %s: old stamp \"schema\": 1, read as timeline/1" % path], []
    return ["WARN %s: no timeline/1 stamp on the meta line (schema=%r), read as timeline/1"
            % (path, stamp)], []
