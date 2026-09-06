def node(name, text="", children=None):
    return [name, [], text, children or []]


def event(onset, duration, voice="1", kind="note", staff="1", time_modification=None):
    return {
        "id": "event-%s-%s" % (voice, onset), "onset": str(onset),
        "duration": str(duration), "voice": voice, "staff": staff,
        "kind": kind, "grace": False, "timeModification": time_modification,
    }


def measure(identifier, number, events, implicit=False, source_region=None, time=None):
    return {
        "id": identifier,
        "location": {"part": 1, "measureIndex": number, "measure": str(number),
                     "page": 1, "system": 1},
        "events": events, "marks": [], "implicit": implicit, "nonControlling": False,
        "context": {"time": {"1": time or [node("beats", "4"), node("beat-type", "4")]},
                    "key": {}, "clef": {}},
        "sourceRegion": source_region,
    }


def score(measures):
    return {"parts": [{"id": "p1", "measures": measures}]}


def test_internal_gap_is_detected_per_voice_without_inventing_rest(api):
    from score_rhythm_gaps import detect_rhythm_gaps, rhythm_gap_issues
    current = measure("p1-m2", 2, [
        event(0, 1), event(2, 1), event(3, 1),
    ], source_region={"page": 1, "coordinateSystem": "pdf_points_top_left",
                      "bbox": [100, 200, 300, 280]})
    report = detect_rhythm_gaps(score([measure("p1-m1", 1, [event(0, 4)]), current,
                                       measure("p1-m3", 3, [event(0, 4)])]))
    assert report["summary"]["gapCount"] == 1
    gap = report["gaps"][0]
    assert (gap["onset"], gap["duration"], gap["position"]) == ("1", "1", "internal")
    assert gap["autoRepairAllowed"] is False
    assert gap["notationConfidence"] == "unknown"
    assert gap["location"]["positionInSystem"] == 2
    assert gap["reviewRegion"]["basis"] == "measure_bbox_linear_time_hint"
    assert rhythm_gap_issues(report)[0]["code"] == "missing_rhythm_duration"


def test_each_voice_has_an_independent_timeline(api):
    from score_rhythm_gaps import detect_rhythm_gaps
    current = measure("p1-m2", 2, [
        event(0, 4, voice="1"), event(1, 2, voice="2"),
    ])
    report = detect_rhythm_gaps(score([measure("p1-m1", 1, [event(0, 4)]), current,
                                       measure("p1-m3", 3, [event(0, 4)])]))
    assert [(item["voice"], item["onset"], item["duration"])
            for item in report["gaps"]] == [("2", "0", "1"), ("2", "3", "1")]
    assert all("multiple_voices" in item["riskReasons"] for item in report["gaps"])


def test_empty_middle_measure_becomes_full_measure_hypothesis(api):
    from score_rhythm_gaps import detect_rhythm_gaps
    measures = [measure("p1-m1", 1, [event(0, 4)]),
                measure("p1-m2", 2, []),
                measure("p1-m3", 3, [event(0, 4)])]
    report = detect_rhythm_gaps(score(measures))
    assert [(item["measureId"], item["duration"], item["position"])
            for item in report["gaps"]] == [("p1-m2", "4", "full_measure")]


def test_implicit_pickup_and_multirest_are_excluded(api):
    from score_rhythm_gaps import detect_rhythm_gaps
    pickup = measure("p1-m1", 1, [event(0, 1)], implicit=True)
    multirest = measure("p1-m2", 2, [event(0, 4, kind="rest")])
    multirest["marks"] = [{"data": node("measure-style", children=[node("multiple-rest", "8")])}]
    report = detect_rhythm_gaps(score([pickup, multirest]))
    assert report["gaps"] == []
    assert {item["reason"] for item in report["exceptions"]} == {
        "implicit_or_non_controlling_measure", "multi_measure_rest"}


def test_composite_time_and_overflow_are_rational(api):
    from score_rhythm_gaps import detect_rhythm_gaps, time_duration
    signature = [node("beats", "3+2"), node("beat-type", "8")]
    assert str(time_duration(signature)) == "5/2"
    current = measure("p1-m2", 2, [event(0, 3)], time=signature)
    report = detect_rhythm_gaps(score([measure("p1-m1", 1, [event(0, "5/2")], time=signature),
                                       current,
                                       measure("p1-m3", 3, [event(0, "5/2")], time=signature)]))
    assert report["summary"]["overflowCount"] == 1
    assert report["overflows"][0]["actualEnd"] == "3"
