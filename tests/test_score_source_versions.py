import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))


def source_tree():
    return ET.fromstring('''<score-partwise><part id="P1"><measure number="1">
      <attributes><divisions>4</divisions><key><fifths>0</fifths></key></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch>
      <duration>4</duration><voice>1</voice><type>quarter</type></note>
    </measure></part></score-partwise>''')


def test_visible_target_pitch_is_written_back_to_source_and_round_trips():
    from score_editor import apply_edits
    from score_source_versions import (assert_target_pitch_changes,
                                       target_pitch_changes_to_source)
    from score_transposition import transpose_tree

    source = source_tree()
    target = copy.deepcopy(source)
    transpose_tree(target, -1, "auto", "clarinet_a", "clarinet_bb")
    change = {"eventId": "p1-m1-n1",
              "pitch": {"step": "C", "alter": 0, "octave": 5}}
    mapped = target_pitch_changes_to_source(source, target, [change], -1)
    assert mapped == [{"eventId": "p1-m1-n1",
                       "pitch": {"step": "D", "alter": -1, "octave": 5}}]
    apply_edits(source, mapped)
    regenerated = copy.deepcopy(source)
    transpose_tree(regenerated, -1, "auto", "clarinet_a", "clarinet_bb")
    assert assert_target_pitch_changes(regenerated, [change])


def test_source_writeback_rejects_mismatched_event_structures():
    from score_source_versions import target_pitch_changes_to_source
    source = source_tree()
    target = copy.deepcopy(source)
    target.find(".//measure").append(ET.fromstring(
        "<note><rest/><duration>4</duration><voice>1</voice></note>"))
    with pytest.raises(ValueError, match="事件结构不一致"):
        target_pitch_changes_to_source(source, target, [{
            "eventId": "p1-m1-n1",
            "pitch": {"step": "C", "alter": 0, "octave": 5},
        }], -1)


def test_validated_target_edit_log_does_not_replace_pitch_mapping_payload():
    from score_editor import apply_edits
    from score_source_versions import target_pitch_changes_to_source
    from score_transposition import transpose_tree

    source = source_tree()
    target = copy.deepcopy(source)
    transpose_tree(target, -1, "auto", "clarinet_a", "clarinet_bb")
    pitch_change = {"eventId": "p1-m1-n1",
                    "pitch": {"step": "C", "alter": 0, "octave": 5}}
    validation_log = apply_edits(copy.deepcopy(target), [pitch_change])
    assert set(validation_log[0]) == {"eventId", "before", "after"}

    mapped = target_pitch_changes_to_source(source, target, [pitch_change], -1)
    apply_edits(source, mapped)
    assert source.findtext(".//pitch/step") == "D"
    assert source.findtext(".//pitch/alter") == "-1"
